"""AS TELAS DA CENTRAL ONRTDPJ — a fila de lá, e o que sobe daqui.

    «ou encaminhamento pela ONRTDPJ para os eletrônicos» — o oficial,
    03/09/2026

O QUE ESTES TESTES GUARDAM
      - **sem token, a tela DIZ onde pegá-lo** e não oferece botão nenhum — o
        token da Central não está num lugar óbvio: é o do SINTER, em Serviços;
      - **a falha da Central aparece escrita**, e não vira lista vazia: um zero
        aqui pode ser «nada chegou» ou «a Central está fora do ar», e as duas
        pedem providências diferentes;
      - **trazer o pedido lança no MESMO Livro de Protocolo** do título de
        papel, e trazer duas vezes **não duplica**;
      - **a atribuição é escolhida, e não deduzida** — o que a «especialidade»
        do contrato vale para separar RTD de RCPJ não foi medido;
      - a rota **fala com a Central FORA da transação** — `BEGIN IMMEDIATE`
        preso numa chamada de rede põe a casa no `busy_timeout`;
      - **só sobe o que já foi decidido e lavrado aqui**: a nota devolutiva
        exige qualificação negativa, e o registro exige ato lavrado;
      - e **enviar não é do balcão**.

NENHUM DESTES TESTES FALA COM A CENTRAL. O transporte é trocado por um de
mentira; o que se prova é a TELA, e a tela é o que faltou seis vezes neste
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

import centrais_cred as CRED
import onrtdpj_api as ONR
import rg_titulo as TIT

SENHA = "Senha#12345"

# Um `PedidoModel` como o contrato o declara — os campos que a tela usa, com a
# grafia de lá (maiúscula inicial). Ver `FONTES_EXTERNAS/onrtdpj/swagger_v1.json`.
PEDIDO = {
    "Protocolo": "2026.000123",
    "DataCadastro": "2026-09-01T14:22:00",
    "Cliente": {"Nome": "ASSOCIAÇÃO DOS BARQUEIROS",
                "CPFCNPJ": "00000010000127",
                "Email": "contato@exemplo.org", "Celular": "(99) 99999-0000"},
    "Servico": {"Id": 3, "Nome": "Registro de documento",
                "Especialidade": "RTD"},
    "Situacao": {"Id": 1, "Nome": "Aguardando cartório"},
    "DescricaoResumida": "Estatuto e ata de fundação",
    "ValorOrcamento": 0.0,
    "LinkArquivoEnviado": "https://centralinside.rtdbrasil.org.br/arq/1",
    "NotaDevolutivaAtiva": False,
}


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


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
    monkeypatch.setattr(ONR, "tem_credencial", lambda **k: True)


@pytest.fixture()
def sem_token(monkeypatch):
    """O espelho de `com_token`: **sem** token, e declarado.

    **ESTE TESTE MEDIA A MÁQUINA, E NÃO A TELA** — medido em 18/09/2026. Ele
    perguntava «a tela diz onde pegar o token quando ele não está informado?» e
    respondia com a pasta de credenciais de `%PROGRAMDATA%`: ficou verde
    enquanto `onrtdpj.cred` não existia, e ficou **vermelho em 12/09/2026**, no
    dia em que o oficial informou o token — sem uma linha de código mudar.

    O `com_token` já declarava a premissa dele; esta é a que faltava. É a régua
    da casa pelo outro lado: teste de domínio escrito à mão preenche tudo e
    passa — este herdava o preenchimento do disco.
    """
    monkeypatch.setattr(ONR, "tem_credencial", lambda **k: False)


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------- sem token, e com falha


def test_sem_token_a_tela_DIZ_onde_pegar(s, sem_token):
    """Recusa que não diz o que fazer manda o oficial procurar — e o token da
    Central não está num lugar óbvio: é o do SINTER, em Serviços."""
    html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
    assert "token da Central ainda não foi informado" in html
    assert "SINTER" in html
    # **O BOTÃO, E NÃO A PALAVRA.** A primeira versão procurava «Trazer» solto,
    # e batia no item de menu «Trazer o acervo do E-Ofício» — a nona vez que um
    # varredor deste projeto acha a palavra fora do que quer medir, e a segunda
    # no mesmo dia. As duas em teste meu.
    assert "/rcpj-rtd/onrtdpj/trazer" not in html, (
        "ofereceu o botão de trazer sem token")


def test_a_falha_da_central_aparece_escrita(s, com_token, monkeypatch):
    """**Um zero pode ser «nada chegou» ou «a Central caiu»**, e as duas pedem
    providências diferentes. Lista vazia calada faria o escrevente achar que
    não há trabalho."""
    def cai(**kw):
        raise ONR.OnrtdpjError("Não consegui falar com a Central ONRTDPJ.")
    monkeypatch.setattr(ONR, "pendentes", cai)
    html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
    assert "Não deu para falar com a Central" in html
    assert "e não porque não haja pedidos" in html


def test_fila_vazia_de_verdade_diz_que_a_consulta_FUNCIONOU(s, com_token,
                                                            monkeypatch):
    monkeypatch.setattr(ONR, "pendentes", lambda **kw: [])
    html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
    assert "Nada esperando na Central agora" in html
    # A FRASE QUEBRA A LINHA no modelo, e HTML não se compara com espaço
    # colado: procura-se o pedaço que sobrevive à quebra.
    assert "consulta funcionou" in html


def test_a_tela_diz_que_o_ambiente_e_o_DE_VERDADE(s, com_token, monkeypatch):
    """**O contrato declara um host só.** Quem achasse que está testando
    estaria falando com a Central de verdade — e o pior número inventado é o
    endereço de homologação que não existe."""
    monkeypatch.setattr(ONR, "pendentes", lambda **kw: [])
    html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
    assert "ambiente só, e é o de produção" in html
    assert "acontece de verdade" in html


# ------------------------------------------------------- a fila e o trazer


def test_a_fila_mostra_o_que_a_central_devolveu(s, com_token, monkeypatch):
    monkeypatch.setattr(ONR, "pendentes", lambda **kw: [PEDIDO])
    html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
    assert "2026.000123" in html
    assert "ASSOCIAÇÃO DOS BARQUEIROS" in html
    assert "Aguardando cartório" in html
    assert "o arquivo, na Central" in html


def test_trazer_lanca_no_livro_de_protocolo(s, com_token, monkeypatch):
    """**O título da Central entra no MESMO livro do de papel.** Duas
    numerações fariam dois títulos com o mesmo número de ordem no mesmo livro,
    que é a pior coisa que pode acontecer a um protocolo."""
    monkeypatch.setattr(ONR, "pedido", lambda p, **kw: PEDIDO)
    html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
    s["c"].post("/rcpj-rtd/onrtdpj/trazer?atribuicao=4",
                data={"csrf_token": _token(html), "protocolo": "2026.000123"},
                follow_redirects=True)
    con = _con(s)
    t = con.execute("SELECT * FROM rg_titulos ORDER BY id DESC LIMIT 1").fetchone()
    lugar = con.execute("SELECT * FROM nu_lugares WHERE tabela='rg_titulos' "
                        "AND referencia=?", (t["id"],)).fetchone()
    enc = con.execute("SELECT * FROM rg_encaminhamentos WHERE titulo_id=?",
                      (t["id"],)).fetchone()
    con.close()
    assert t["numero"] == 1 and lugar
    assert t["forma"] == TIT.ELETRONICO
    assert t["origem"] == TIT.ORIGEM_DA_CENTRAL
    assert t["origem_chave"] == "2026.000123"
    assert t["apresentante"] == "ASSOCIAÇÃO DOS BARQUEIROS"
    # A DATA DE ENTRADA É A DA CENTRAL, e não a de hoje: baixar a fila com
    # atraso não pode mudar a prioridade de quem apresentou primeiro.
    assert t["data_apresentacao"] == "2026-09-01"
    assert enc["sentido"] == TIT.RECEBIDO
    assert enc["protocolo_central"] == "2026.000123"


def test_trazer_duas_vezes_NAO_duplica(s, com_token, monkeypatch):
    """A fila de lá traz o mesmo pedido todo dia até alguém tratá-lo; sem a
    chave de origem, cada baixada abriria um protocolo novo aqui."""
    monkeypatch.setattr(ONR, "pedido", lambda p, **kw: PEDIDO)
    for _ in range(2):
        html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
        s["c"].post("/rcpj-rtd/onrtdpj/trazer?atribuicao=4",
                    data={"csrf_token": _token(html),
                          "protocolo": "2026.000123"}, follow_redirects=True)
    con = _con(s)
    quantos = con.execute("SELECT COUNT(*) n FROM rg_titulos").fetchone()["n"]
    con.close()
    assert quantos == 1


def test_o_que_ja_veio_nao_oferece_botao_de_trazer(s, com_token, monkeypatch):
    monkeypatch.setattr(ONR, "pendentes", lambda **kw: [PEDIDO])
    monkeypatch.setattr(ONR, "pedido", lambda p, **kw: PEDIDO)
    html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
    s["c"].post("/rcpj-rtd/onrtdpj/trazer?atribuicao=4",
                data={"csrf_token": _token(html), "protocolo": "2026.000123"},
                follow_redirects=True)
    html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
    assert "já está no protocolo" in html
    assert "abrir protocolo n." in html
    assert "/rcpj-rtd/titulo/" in html


def test_a_atribuicao_e_ESCOLHIDA_e_a_tela_diz_por_que(s, com_token,
                                                       monkeypatch):
    """**O que a «especialidade» do contrato vale para separar RTD de RCPJ não
    foi medido** — não há um pedido real desta serventia para conferir."""
    monkeypatch.setattr(ONR, "pendentes", lambda **kw: [PEDIDO])
    monkeypatch.setattr(ONR, "pedido", lambda p, **kw: PEDIDO)
    html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
    assert "escolhida por você, e não deduzida" in html
    s["c"].post("/rcpj-rtd/onrtdpj/trazer?atribuicao=3",
                data={"csrf_token": _token(html), "protocolo": "2026.000123"},
                follow_redirects=True)
    con = _con(s)
    t = con.execute("SELECT atribuicao FROM rg_titulos ORDER BY id DESC "
                    "LIMIT 1").fetchone()
    con.close()
    assert t["atribuicao"] == TIT.RCPJ, "a tela ignorou a atribuição escolhida"


def test_a_recusa_da_central_ao_trazer_vira_frase(s, com_token, monkeypatch):
    def cai(p, **kw):
        raise ONR.OnrtdpjRecusou("A Central ONRTDPJ não encontrou o pedido.")
    monkeypatch.setattr(ONR, "pedido", cai)
    html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
    r = s["c"].post("/rcpj-rtd/onrtdpj/trazer?atribuicao=4",
                    data={"csrf_token": _token(html), "protocolo": "x"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "não encontrou o pedido" in r.get_data(as_text=True)


# ------------------------------------------------------- o que SOBE daqui


def _trazido(s, monkeypatch) -> int:
    monkeypatch.setattr(ONR, "pedido", lambda p, **kw: PEDIDO)
    html = s["c"].get("/rcpj-rtd/onrtdpj").get_data(as_text=True)
    s["c"].post("/rcpj-rtd/onrtdpj/trazer?atribuicao=4",
                data={"csrf_token": _token(html), "protocolo": "2026.000123"},
                follow_redirects=True)
    con = _con(s)
    t = con.execute("SELECT id FROM rg_titulos ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    return int(t["id"])


def _qualificar(s, titulo_id, resultado, **campos):
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "resultado": resultado}
    dados.update(campos)
    s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/qualificar", data=dados,
                follow_redirects=True)


def test_a_ficha_do_titulo_da_central_mostra_o_protocolo_de_la(s, com_token,
                                                               monkeypatch):
    titulo_id = _trazido(s, monkeypatch)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    assert "veio da Central sob o protocolo" in html
    assert "2026.000123" in html


def test_a_nota_devolutiva_sobe_o_TEXTO_QUE_FOI_LAVRADO(s, com_token,
                                                        monkeypatch):
    """**Dois textos para a mesma exigência divergiriam**, e o que a Central
    mostrasse não seria o que a serventia lavrou."""
    titulo_id = _trazido(s, monkeypatch)
    _qualificar(s, titulo_id, TIT.NEGATIVA,
                exigencias="Falta a ata de eleição da diretoria, assinada.")
    subiu = {}

    def cadastrar(protocolo, descricao, **kw):
        subiu.update({"protocolo": protocolo, "descricao": descricao})
        return 9999
    monkeypatch.setattr(ONR, "cadastrar_nota_devolutiva", cadastrar)

    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    r = s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/onrtdpj/nota",
                    data={"csrf_token": _token(html)}, follow_redirects=True)
    assert subiu["protocolo"] == "2026.000123"
    assert subiu["descricao"] == "Falta a ata de eleição da diretoria, assinada."
    assert "9999" in r.get_data(as_text=True)
    con = _con(s)
    enviados = con.execute(
        "SELECT * FROM rg_encaminhamentos WHERE titulo_id=? AND sentido=?",
        (titulo_id, TIT.ENVIADO)).fetchall()
    con.close()
    assert len(enviados) == 1


def test_nao_sobe_nota_de_titulo_sem_qualificacao_negativa(s, com_token,
                                                           monkeypatch):
    titulo_id = _trazido(s, monkeypatch)
    _qualificar(s, titulo_id, TIT.POSITIVA)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    r = s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/onrtdpj/nota",
                    data={"csrf_token": _token(html)}, follow_redirects=True)
    assert "qualificação negativa" in r.get_data(as_text=True)


def test_so_se_informa_a_central_o_registro_JA_LAVRADO(s, com_token,
                                                       monkeypatch):
    """**Um botão que informasse a Central sem o ato lavrado poria no mundo um
    registro que o livro não tem.**"""
    titulo_id = _trazido(s, monkeypatch)
    _qualificar(s, titulo_id, TIT.POSITIVA)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    r = s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/onrtdpj/registro",
                    data={"csrf_token": _token(html)}, follow_redirects=True)
    assert "já foi lavrado aqui" in r.get_data(as_text=True)


def test_o_registro_informado_leva_o_numero_do_LIVRO_DESTA_CASA(s, com_token,
                                                                monkeypatch):
    titulo_id = _trazido(s, monkeypatch)
    _qualificar(s, titulo_id, TIT.POSITIVA)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/registrar",
                data={"csrf_token": _token(html), "serie": "TD_B",
                      "teor": "Registro integral."}, follow_redirects=True)
    subiu = {}
    monkeypatch.setattr(ONR, "registrar_pedido",
                        lambda p, **kw: subiu.update({"protocolo": p, **kw}))
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/onrtdpj/registro",
                data={"csrf_token": _token(html)}, follow_redirects=True)
    assert subiu["protocolo"] == "2026.000123"
    assert subiu["numero_registro"] == "1"


def test_titulo_que_nao_veio_da_central_nao_sobe(s):
    """Sem protocolo de lá não há o que informar — e a tela diz o que fazer."""
    html = s["c"].get("/rcpj-rtd/titulos/novo").get_data(as_text=True)
    s["c"].post("/rcpj-rtd/titulos/novo?atribuicao=4",
                data={"csrf_token": _token(html),
                      "data_apresentacao": "2026-09-03",
                      "apresentante": "FULANO"}, follow_redirects=True)
    con = _con(s)
    titulo_id = con.execute("SELECT id FROM rg_titulos ORDER BY id DESC "
                            "LIMIT 1").fetchone()["id"]
    con.close()
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    assert "não veio da Central" in html
    # AS QUATRO ROTAS QUE FALAM COM A CENTRAL recusam do mesmo jeito, e a
    # recusa **diz o que falta** — sem o protocolo de lá não há o que informar.
    for caminho in ("registro", "nota", "orcamento", "cancelar"):
        r = s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/onrtdpj/{caminho}",
                        data={"csrf_token": _token(html)},
                        follow_redirects=True)
        assert "não tem protocolo na Central" in r.get_data(as_text=True), caminho


# --------------------------------------------------- a rede fora da trava


def test_a_chamada_da_central_fica_FORA_da_transacao():
    """**`db.transaction()` é `BEGIN IMMEDIATE`**, e segurá-lo durante uma
    chamada de trinta segundos poria todo outro balcão no `busy_timeout`.
    Primeiro se pergunta à Central; depois se grava."""
    fonte = (RAIZ / "rg_web.py").read_text(encoding="utf-8")
    dentro = []
    for bloco in fonte.split("with db.transaction() as con:")[1:]:
        # o corpo do `with` vai até a próxima linha com menos indentação
        corpo = []
        for linha in bloco.splitlines()[1:]:
            if linha.strip() and not linha.startswith(" " * 16):
                break
            corpo.append(linha)
        texto = "\n".join(corpo)
        dentro += [x for x in ("ONR.pedido(", "ONR.pendentes(",
                               "ONR.cadastrar_nota_devolutiva(",
                               "ONR.registrar_pedido(", "ONR.diagnostico(")
                   if x in texto]
    assert not dentro, (
        f"chamada de rede dentro do BEGIN IMMEDIATE: {dentro}")


# ---------------------------------------------------------- quem entra


def test_enviar_a_central_nao_e_do_balcao(cg_casa, monkeypatch):
    """**O que sobe muda coisa na Central**, e por isso não é do balcão — a
    mesma separação da CENPROT e da ajuda do Claude."""
    monkeypatch.setattr(ONR, "tem_credencial", lambda **k: True)
    s = _sessao(cg_casa, papel="USER")
    monkeypatch.setattr(ONR, "pedido", lambda p, **kw: PEDIDO)
    titulo_id = _trazido(s, monkeypatch)
    token = _token(s["c"].get("/rcpj-rtd/titulos/novo").get_data(as_text=True))
    for caminho in ("onrtdpj/nota", "onrtdpj/registro"):
        r = s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/{caminho}",
                        data={"csrf_token": token})
        assert r.status_code in (302, 403), (
            f"a rota /{caminho} aceitou quem não decide (HTTP {r.status_code})")
    r = s["c"].post("/rcpj-rtd/onrtdpj/testar", data={"csrf_token": token})
    assert r.status_code in (302, 403)


def test_o_balcao_TRAZ_o_pedido(cg_casa, monkeypatch):
    """Trazer é receber título — isso é do balcão, como receber o de papel."""
    monkeypatch.setattr(ONR, "tem_credencial", lambda **k: True)
    monkeypatch.setattr(ONR, "pedido", lambda p, **kw: PEDIDO)
    s = _sessao(cg_casa, papel="USER")
    assert _trazido(s, monkeypatch)


def test_a_tela_da_central_esta_no_menu(s):
    html = s["c"].get("/rcpj-rtd/titulos").get_data(as_text=True)
    assert 'href="/rcpj-rtd/onrtdpj"' in html


def test_a_configuracao_oferece_o_campo_de_TOKEN(s):
    """A ONRTDPJ guarda um token, e não um par: um campo de usuário faria
    alguém preenchê-lo com o CNS só para a tela deixar salvar."""
    # A ROTA SE CHAMA `settings` E O ENDEREÇO É `/configuracoes` — o mesmo
    # descasamento que já custou um `url_for` errado neste projeto. Aqui se usa
    # o `url_for`, que é quem sabe.
    html = s["c"].get(s["app"].url_map.bind("x").build("settings")
                      ).get_data(as_text=True)
    assert CRED.NOME_DA_CENTRAL[CRED.ONRTDPJ] in html
    assert 'name="token"' in html
    assert "Envio Extrato SINTER" in html
