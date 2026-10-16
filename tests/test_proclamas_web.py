"""AS TELAS DO e-PROCLAMAS — a fila, a conferencia e o envio.

O QUE ESTES TESTES GUARDAM, e cada um custou uma decisao:

      - **sem token, a tela DIZ onde pegar** e nao oferece botao de enviar — e
        ela diz tambem que o token e o MESMO da API de certidao, porque um
        cadastro serve as duas;
      - **o teste de ligacao nao prova o token**, e a tela separa as duas
        frases: `health` nao leva autenticacao (medido), e quem confundir isso
        conclui que a credencial esta boa porque a Central respondeu;
      - **o que vai em branco aparece ANTES de subir** — em especial o
        endereco, que nao vai;
      - **enviar nao e do balcao**;
      - a rota **fala com a Central FORA da transacao**;
      - e **a recusa da Central vira aviso na tela**, e nao HTTP 500.

NENHUM DESTES TESTES FALA COM A CENTRAL. O transporte e trocado por um de
mentira; o que se prova e a TELA — e a tela e o que faltou seis vezes neste
projeto.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import habilitacao as HAB
import onrcpn_api as API
import proclamas as PROC
import rc_assento as RC

SENHA = "Senha#12345"
AGORA = "2026-09-03T10:00:00"
TEOR = ("Faco saber que pretendem casar-se FULANO DE TAL e BELTRANA DE TAL, "
        "e que apresentaram os documentos exigidos pelo art. 1.525 do Codigo "
        "Civil. Quem souber de impedimento, oponha-o na forma da lei.")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return achado.group(1) if achado else ""


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "db": bd}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


@pytest.fixture()
def com_token(monkeypatch):
    """O sistema acha que o token existe, sem gravar segredo nenhum."""
    monkeypatch.setattr(API, "tem_credencial", lambda **k: True)


@pytest.fixture()
def sem_token(monkeypatch):
    """O espelho de `com_token`: **sem** token, e declarado.

    **SEM ISTO O TESTE PERGUNTAVA AO DISCO** — medido em 18/09/2026. Ele ficava
    verde enquanto `onrcpn.cred` não existia em `%PROGRAMDATA%`, e ficaria
    vermelho no dia em que o oficial informasse o token do IdRC — sem uma linha
    de código mudar. E é justamente essa credencial que
    `DOCUMENTACAO/PEDIDO_DAS_CREDENCIAIS.md` foi pedir.

    A premissa é do teste e tem de estar escrita nele: o que se mede aqui é a
    TELA, e não o que a máquina de quem roda a suíte tem gravado.
    """
    monkeypatch.setattr(API, "tem_credencial", lambda **k: False)


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _com_edital(s, *, com_assento: bool = True) -> int:
    """Uma habilitacao com edital publicado — e, se pedido, o Livro D."""
    con = _con(s)
    h = HAB.abrir(con, {
        "nubente1_nome": "FULANO DE TAL", "nubente1_estado_civil": "SOLTEIRO",
        "nubente1_sexo": "M", "nubente1_nascimento": "1990-05-12",
        "nubente1_documento": "000.000.046-93",
        "nubente1_naturalidade": "Cidade Exemplo/MA",
        "nubente1_pai": "JOSE DE TAL", "nubente1_mae": "MARIA DE TAL",
        "nubente1_endereco": "Rua das Flores, 100, Centro",
        "nubente2_nome": "BELTRANA DE TAL", "nubente2_estado_civil": "SOLTEIRA",
        "nubente2_sexo": "F", "nubente2_nascimento": "1992-03-08",
        "tipo": "CIVIL", "regime": "COMUNHAO_PARCIAL"},
        agora=AGORA, usuario="MARIO")
    for d in HAB.o_que_falta(con, h):
        HAB.marcar_documento(con, d["id"], apresentado=True, agora=AGORA,
                             usuario="MARIO")
    HAB.publicar_edital(con, h, teor=TEOR, agora=AGORA, hoje="2026-09-03",
                        usuario="MARIO")
    if com_assento:
        sv = {"ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
              "escrevente": "MARIO", "funcao": "Escrevente"}
        feito = RC.lavrar_assento(
            con, especie="PROCLAMAS", nome="FULANO e BELTRANA", sv=sv,
            agora=AGORA, data_extenso="tres de setembro de dois mil e vinte e "
            "seis", data_fato="2026-09-03", usuario="MARIO")
        con.execute(
            "UPDATE hc_habilitacoes SET proclamas_assento_id=? WHERE id=?",
            (feito["assento_id"], h))
    con.commit()
    con.close()
    return h


# ------------------------------------------------------- sem credencial


def test_sem_token_a_tela_diz_onde_pegar_e_que_ele_serve_as_duas(s, sem_token):
    """Recusa que nao diz o que fazer manda o oficial procurar.

    E aqui ha um fato que poupa trabalho: **o mesmo token serve ao e-Proclamas
    e a API de Certidao Eletronica** — um cadastro so. Quem nao souber disso
    pede duas credenciais.
    """
    html = s["c"].get("/rcpn/proclamas").get_data(as_text=True)
    assert "token do IdRC ainda não foi informado" in html
    # **O QUE ESTE TESTE COBRAVA ERA UMA SUBSTRING QUE OS DOIS ENDEREÇOS TÊM**,
    # e foi assim que ele passou verde com o endereço MORTO na tela. Ele pedia
    # `"solicitacao-novo-client" in html` — e essa metade do caminho existe tanto
    # no host certo quanto no errado. Medido em 18/09/2026: o host antigo devolve
    # **404**, igualzinho a um caminho inventado dentro dele. A régua agora
    # confere o HOST, e recusa o falecido — a lição do varredor que lê a palavra
    # fora do que quer medir, aqui na forma de subcaminho.
    assert "integracao.idrc.registrocivil.org.br" in html
    # **O HOST DE CRIAR O USUÁRIO TEM «H» NO NOME, E O SEM «H» ESTÁ MORTO.**
    # Medido em 18/09/2026: `www.homeh.registrocivil.org.br` responde **302**
    # para o login do IdRC; e `home.registrocivil.org.br` devolve **404 em todos
    # os caminhos medidos**, inclusive no `/solicitacao` que o FAQ do próprio
    # manual cita. O assert de recusa continua valendo porque
    # «homeh.registrocivil.org.br» **não contém** «home.registrocivil.org.br» —
    # e é bom que continue: quem «corrigir» o `homeh` para `home` na tela põe o
    # endereço morto de volta, e é este assert que o pega.
    assert "www.homeh.registrocivil.org.br" in html
    assert "home.registrocivil.org.br" not in html
    # A etapa zero: sem conta no IdRC a página do cadastro não abre.
    assert "usuário IdRC" in html
    assert "mesmo token" in html.lower()


def test_sem_token_a_ficha_nao_oferece_o_botao_de_enviar(s, sem_token):
    h = _com_edital(s)
    html = s["c"].get(f"/rcpn/proclamas/{h}").get_data(as_text=True)
    # **O ENDERECO DO BOTAO, E NAO A PALAVRA.** Procurar «Enviar» solto bateria
    # no titulo da secao e no proprio texto explicativo — e a decima vez que um
    # varredor deste projeto acharia a palavra fora do que quer medir.
    assert f"/rcpn/proclamas/{h}/enviar" not in html


def test_a_tela_diz_por_que_o_ambiente_e_o_de_homologacao(s):
    """**A pergunta de quem lê é «isto é de verdade?»**, e a resposta mudou em
    18/09/2026: o endereço de produção **existe e responde** — o que segura o
    sistema em homologação é a ORDEM que o cadastro exige (o client de produção
    só se cria citando o protocolo do de homologação).

    Até esta data a tela dizia «só há ambiente de homologação publicado», e a
    frase ficou **falsa pela medição**: o endereço não estava publicado no
    contrato, e estava de pé. Quem a lesse concluiria que produção não existe.
    """
    html = s["c"].get("/rcpn/proclamas").get_data(as_text=True)
    assert "homologação" in html
    assert "existem e respondem" in html, \
        "a tela voltou a dizer que só há homologação — o endereço foi medido"
    assert "exige a ordem" in html


# ------------------------------------------------------- a fila


def test_a_fila_traz_quem_publicou_edital(s, com_token):
    h = _com_edital(s)
    html = s["c"].get("/rcpn/proclamas").get_data(as_text=True)
    assert "FULANO DE TAL" in html
    assert f"/rcpn/proclamas/{h}" in html


def test_a_fila_avisa_quando_falta_lavrar_o_livro_D(s, com_token):
    """Sem o assento nao ha matricula, e a coluna diz isso ANTES da ficha."""
    _com_edital(s, com_assento=False)
    html = s["c"].get("/rcpn/proclamas").get_data(as_text=True)
    assert "falta lavrar" in html


def test_fila_vazia_diz_onde_ela_enche(s, com_token):
    """Lista vazia que so mostra nada faz o operador achar que quebrou."""
    html = s["c"].get("/rcpn/proclamas").get_data(as_text=True)
    assert "Nenhuma habilitação está esperando" in html
    assert "etapa 2" in html


# ------------------------------------------------------- a conferencia


def test_a_ficha_mostra_o_que_iria_e_o_que_vai_em_branco(s, com_token):
    h = _com_edital(s)
    html = s["c"].get(f"/rcpn/proclamas/{h}").get_data(as_text=True)
    assert "00000004693" in html            # o CPF ja sem pontuacao
    assert "03/09/2026" in html             # a data ja em dd/mm/aaaa
    assert "endereço" in html.lower()       # e o aviso de que ele nao vai
    # E O TEXTO DO ENDERECO NAO VAZOU para dentro de campo nenhum do proclama.
    assert "Rua das Flores" not in html


def test_a_ficha_mostra_a_procedencia_do_digito_do_livro_D(s, com_token):
    """Quem assina precisa saber que o `6` saiu do exemplo de um contrato."""
    h = _com_edital(s)
    html = s["c"].get(f"/rcpn/proclamas/{h}").get_data(as_text=True)
    assert "Livro D" in html
    assert "e-Proclamas" in html
    assert "fabricado" in html


def test_a_ficha_diz_que_200_nao_e_sinal_de_sucesso(s, com_token):
    """O contrato responde com DUAS listas, e a tela avisa antes de mandar."""
    h = _com_edital(s)
    html = s["c"].get(f"/rcpn/proclamas/{h}").get_data(as_text=True)
    assert "duas listas" in html


# ------------------------------------------------------- quem pode mandar


def test_enviar_nao_e_do_balcao(cg_casa, monkeypatch):
    """Conferir e de quem atende; mandar a Central e do oficial.

    E a separacao da ajuda do Claude — consultar abre, configurar nao — e a da
    CENPROT.
    """
    monkeypatch.setattr(API, "tem_credencial", lambda **k: True)
    s = _sessao(cg_casa, papel="USER")
    h = _com_edital(s)
    # CONFERIR ELE PODE.
    assert s["c"].get(f"/rcpn/proclamas/{h}").status_code == 200
    # MANDAR, NAO. O token vem de uma tela que o USER abre — sem ele a rota
    # devolveria 400 por CSRF e nunca chegaria a guarda de papel.
    csrf = _token(s["c"].get(f"/rcpn/proclamas/{h}").get_data(as_text=True))
    r = s["c"].post(f"/rcpn/proclamas/{h}/enviar",
                    data={"csrf_token": csrf, "publicacao": "1"})
    assert r.status_code in (302, 403)
    if r.status_code == 302:
        assert "/rcpn/proclamas" not in r.headers.get("Location", "")


# ------------------------------------------------------- o envio


def test_a_recusa_da_central_vira_aviso_e_nao_HTTP_500(s, com_token,
                                                       monkeypatch):
    """A Central RECEBEU e RECUSOU — e isso nao e erro de programa.

    O envio fica registrado, porque a chamada aconteceu e pode ter sido
    cobrada; o que nao acontece e a publicacao contar como feita.
    """
    h = _com_edital(s)

    def falso(cns, proclamas, **k):
        matricula = proclamas[0]["matricula"]
        return {"enviados": 1, "corpo_enviado": {"cns": cns,
                                                 "proclamas": proclamas},
                "resposta": {"status": "success"},
                "lote": "9", "aceitos": [],
                "recusados": [{"matricula": matricula,
                               "message": "the procedure request failed",
                               "details": "Foi encontrado um ou mais erros",
                               "errors": [{"field": "sexo_genitor",
                                           "message": "Informar masculino ou "
                                                      "feminino"}]}],
                "entendi": True}

    monkeypatch.setattr(API, "enviar", falso)
    html = s["c"].get(f"/rcpn/proclamas/{h}").get_data(as_text=True)
    r = s["c"].post(f"/rcpn/proclamas/{h}/enviar",
                    data={"csrf_token": _token(html), "publicacao": "1"},
                    follow_redirects=True)
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "RECUSOU" in texto
    assert "sexo_genitor" in texto

    # O ENVIO FICOU REGISTRADO, E **SEM** NUMERO DE LOTE.
    con = _con(s)
    linhas = PROC.enviados_de(con, h)
    assert len(linhas) == 1 and not linhas[0]["protocolo"]
    # E A HABILITACAO NAO GANHOU PROTOCOLO NENHUM.
    assert not con.execute(
        "SELECT eproclamas_protocolo FROM hc_habilitacoes WHERE id=?",
        (h,)).fetchone()[0]
    con.close()


def test_o_envio_aceito_grava_o_lote_e_o_protocolo_da_habilitacao(
        s, com_token, monkeypatch):
    """O numero do lote entra por onde o protocolo ja entrava.

    `habilitacao.registrar_publicacao` e quem grava `eproclamas_protocolo`
    desde 28/08, e continua sendo — dois caminhos escrevendo o mesmo fato
    divergiriam no primeiro conserto.
    """
    h = _com_edital(s)

    def falso(cns, proclamas, **k):
        return {"enviados": 1, "corpo_enviado": {"cns": cns,
                                                 "proclamas": proclamas},
                "resposta": {"status": "success"}, "lote": "77",
                "aceitos": [proclamas[0]["matricula"]], "recusados": [],
                "entendi": True}

    monkeypatch.setattr(API, "enviar", falso)
    html = s["c"].get(f"/rcpn/proclamas/{h}").get_data(as_text=True)
    r = s["c"].post(f"/rcpn/proclamas/{h}/enviar",
                    data={"csrf_token": _token(html), "publicacao": "1"},
                    follow_redirects=True)
    assert "lote" in r.get_data(as_text=True).lower()

    con = _con(s)
    assert PROC.enviados_de(con, h)[0]["protocolo"] == "77"
    assert con.execute(
        "SELECT eproclamas_protocolo FROM hc_habilitacoes WHERE id=?",
        (h,)).fetchone()[0] == "77"
    con.close()


def test_a_rota_fala_com_a_central_FORA_da_transacao(s, com_token,
                                                     monkeypatch):
    """`BEGIN IMMEDIATE` preso numa chamada de rede poe a casa no busy_timeout.

    O guarda: durante o envio, uma SEGUNDA conexao tem de conseguir escrever.
    Se a rota estivesse com a transacao aberta, este `INSERT` esperaria o
    `busy_timeout` inteiro e falharia.
    """
    h = _com_edital(s)
    escreveu = {}

    def falso(cns, proclamas, **k):
        outra = sqlite3.connect(s["banco"], timeout=1)
        try:
            outra.execute(
                "INSERT INTO hc_andamento(habilitacao_id, quando, o_que) "
                "VALUES(?,?,?)", (h, AGORA, "escrita durante a chamada"))
            outra.commit()
            escreveu["ok"] = True
        finally:
            outra.close()
        return {"enviados": 1, "corpo_enviado": {"cns": cns,
                                                 "proclamas": proclamas},
                "resposta": {}, "lote": "1",
                "aceitos": [proclamas[0]["matricula"]], "recusados": [],
                "entendi": True}

    monkeypatch.setattr(API, "enviar", falso)
    html = s["c"].get(f"/rcpn/proclamas/{h}").get_data(as_text=True)
    s["c"].post(f"/rcpn/proclamas/{h}/enviar",
                data={"csrf_token": _token(html), "publicacao": "1"},
                follow_redirects=True)
    assert escreveu.get("ok"), (
        "a casa ficou travada durante a chamada a Central")


def test_o_teste_de_ligacao_nao_afirma_nada_sobre_o_token(s, monkeypatch):
    """`health` nao leva autenticacao — medido, e nao deduzido.

    Quem confundir as duas coisas conclui que a credencial esta boa porque a
    Central respondeu.
    """
    monkeypatch.setattr(API, "esta_no_ar", lambda **k: {
        "no_ar": True, "status": 200,
        "resposta": "Conexão com Oracle realizada com sucesso"})
    html = s["c"].get("/rcpn/proclamas").get_data(as_text=True)
    r = s["c"].post("/rcpn/proclamas/testar",
                    data={"csrf_token": _token(html)}, follow_redirects=True)
    texto = r.get_data(as_text=True)
    assert "Oracle" in texto
    assert "não** prova o token" in texto or "não</strong> prova" in texto \
        or "prova o token" in texto
