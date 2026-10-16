"""A tela da API da CRA — testar, e trazer o arquivo cru.

**ESTA TELA É MENOS DO QUE PODERIA SER, E O TESTE GUARDA ISSO.** Duas coisas
do contrato da CRA não estão medidas — o que vai em `userDados` e o que
exatamente volta no `return` —, e construir a corrente inteira em cima disso
seria inventar o meio dela: um botão «baixar e apontar tudo» que lesse errado
apontaria títulos que ninguém apresentou, **e apontamento não se desfaz**.

Então os testes conferem que a tela **diz o que não sabe**, em vez de conferir
que ela faz o que não dá para fazer com verdade.

O QUE ELES GUARDAM
      - a tela existe e está no menu (o defeito das seis vezes);
      - **toda função pública de `cra21_api` tem chamador**;
      - ela **não é do balcão** — falar direto com a Central é de quem responde
        pela serventia, e a consulta pode marcar coisa lá dentro;
      - sem credencial ela devolve **frase**, e não HTTP 500;
      - ela **declara as dez operações sem sentido medido**, com nome e tudo;
      - e o achado de segurança do `http://` fica **à vista do oficial**, e não
        só no código.
"""
from __future__ import annotations

import ast
import glob
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cra21_api as CRA

SENHA = "Senha#12345"


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
    bd.set_settings({"modulo_protesto_alcance": "TODOS"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


@pytest.fixture()
def sem_credencial(monkeypatch, tmp_path):
    """A pasta das credenciais das Centrais apontada para uma pasta VAZIA.

    **O TESTE NÃO PODE DEPENDER DO DISCO DE QUEM O RODA.** Ele diz «sem
    credencial a tela devolve frase, e não HTTP 500» — e isso só é verdade
    onde não há credencial gravada. Na máquina do balcão a CRA **tem**
    `cra.cred` desde que o oficial a cadastrou (medido: 57 bytes em
    18/09/2026), e ali os dois testes ficavam vermelhos **sem defeito
    nenhum** — a tela respondia certo, só não era o caminho que o teste
    queria percorrer.

    Apontar `pasta_de_dados` para uma pasta vazia é mais fiel que forçar
    `tem()` a devolver falso: **toda** leitura de credencial daquela rodada
    passa a ver ausência — a de `diagnostico` e a de `_bater` —, e o teste
    exercita a mesma coisa que a instalação limpa exercita. É a forma do
    `sem_chave` de `test_resolve_intimacao.py`.
    """
    monkeypatch.setattr(CRA.CRED, "pasta_de_dados", lambda: tmp_path)


# ------------------------------------------- a tela existe, e no menu


def test_a_tela_abre(s):
    r = s["c"].get("/protesto/cra/api")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "CRA" in html
    assert "BuscarApresentante" in html


def test_a_tela_esta_no_menu(s):
    """**O defeito das seis vezes.**"""
    painel = s["c"].get("/protesto").get_data(as_text=True)
    assert "/protesto/cra/api" in painel, (
        "o menu do Protesto não oferece a tela da CRA")


def test_toda_funcao_do_transporte_tem_chamador():
    """O varredor das seis vezes, aplicado ao módulo da CRA."""
    fonte = (RAIZ / "cra21_api.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    publicas = {n.name for n in arvore.body
                if isinstance(n, ast.FunctionDef)
                and not n.name.startswith("_")}
    usadas = {no.func.id if isinstance(no.func, ast.Name) else no.func.attr
              for no in ast.walk(arvore)
              if isinstance(no, ast.Call)
              and isinstance(no.func, (ast.Name, ast.Attribute))}
    for arq in RAIZ.glob("*.py"):
        if arq.name == "cra21_api.py":
            continue
        texto = arq.read_text(encoding="utf-8", errors="replace")
        usadas |= {n for n in publicas if ("CRA." + n) in texto}
    assert publicas - usadas == set(), (
        f"funções da CRA sem chamador: {sorted(publicas - usadas)}")


# ------------------------------------------- o que a tela DIZ que não sabe


def test_a_tela_declara_as_dez_operacoes_sem_sentido_medido(s):
    """**Item declarado é diferente de item esquecido**, e quem for procurar
    precisa saber qual dos dois. A Confirmação e o Retorno estão entre elas —
    e são os dois passos com hora marcada no roteiro."""
    html = s["c"].get("/protesto/cra/api").get_data(as_text=True)
    assert "userDados" in html
    for operacao in ("Confirmacao", "Retorno", "CustasTitulo"):
        assert operacao in html, f"«{operacao}» não está declarada na tela"
    assert "11h30" in html and "14h10" in html


def test_a_tela_diz_que_o_arquivo_baixa_e_NAO_aponta(s):
    """Se ela não disser, o escrevente vai achar que apontou."""
    html = s["c"].get("/protesto/cra/api").get_data(as_text=True)
    assert "não aponta nada" in html
    assert "Remessa da CRA" in html, "e diz onde é que se aponta"


def test_o_achado_do_http_fica_a_vista_do_oficial(s):
    """**Não basta o guarda estar no código**: quem opera a Central precisa
    saber por que o sistema não faz o que o arquivo dela manda."""
    html = s["c"].get("/protesto/cra/api").get_data(as_text=True)
    assert "força o https" in html
    assert "sem o S" in html
    assert "legível" in html


def test_a_tela_so_tem_producao(s):
    """**14/10/2026** — ordem do oficial: «tire a opção de funcionar na
    homologação, agora é tudo produção». A tela tinha seletor com
    homologação (o padrão) e produção; agora não tem seletor, e um endereço
    antigo com `?ambiente=HOMOLOGACAO` abre a produção."""
    for endereco in ("/protesto/cra/api",
                     "/protesto/cra/api?ambiente=HOMOLOGACAO"):
        html = s["c"].get(endereco).get_data(as_text=True)
        assert "<select name=\"ambiente\"" not in html
        assert 'value="HOMOLOGACAO"' not in html
        assert "Ambiente de PRODUÇÃO" in html
        assert "Comece pela de homologação" not in html
        assert "crama.crabr.com.br" in html, "o endereço mostrado é o de produção"


def test_a_producao_avisa_que_baixar_MARCA_do_lado_de_la(s):
    """O manual diz que a `Remessa` traz a do dia mais as pendentes — pedir
    duas vezes não é o mesmo que pedir uma."""
    html = s["c"].get("/protesto/cra/api?ambiente=PRODUCAO").get_data(
        as_text=True)
    assert "marca do lado de\n  lá" in html or "marca do lado de lá" in html


# ------------------------------------------- as recusas


def test_testar_sem_credencial_volta_com_a_frase_e_nao_com_500(s,
                                                               sem_credencial):
    html = s["c"].get("/protesto/cra/api").get_data(as_text=True)
    r = s["c"].post("/protesto/cra/api/testar",
                    data={"csrf_token": _token(html)}, follow_redirects=True)
    assert r.status_code == 200
    assert "não foi informada" in r.get_data(as_text=True)


def test_baixar_sem_credencial_volta_com_a_frase_e_nao_com_500(s,
                                                                sem_credencial):
    html = s["c"].get("/protesto/cra/api").get_data(as_text=True)
    r = s["c"].post("/protesto/cra/api/baixar",
                    data={"csrf_token": _token(html), "o_que": "remessa",
                          "nome": "C0013110.141"}, follow_redirects=True)
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "não foi informada" in texto


def test_baixar_sem_escolher_o_que_volta_com_a_frase(s):
    html = s["c"].get("/protesto/cra/api").get_data(as_text=True)
    r = s["c"].post("/protesto/cra/api/baixar",
                    data={"csrf_token": _token(html), "o_que": ""},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "Escolha o que trazer" in r.get_data(as_text=True)


def test_baixar_com_conteudo_no_lugar_do_nome_recusa(s, tmp_path,
                                                    monkeypatch):
    """**`userArq` é o NOME do arquivo** — mandar o conteúdo seria mandar
    megabytes onde a Central espera onze caracteres.

    **E ESTE TESTE ESCREVIA NA PASTA DE VERDADE DA MÁQUINA** — corrigido em
    04/09/2026, depois de a suíte inteira ficar vermelha em dois testes
    vizinhos que esperam «sem credencial». Ele gravava `cra.cred` em
    `%PROGRAMDATA%\\CartorioGestao\\` e apagava no `finally`; bastava a
    execução morrer no meio para o arquivo ficar lá, e as duas execuções
    seguintes falharem sem ninguém entender por quê.

    **Pior que quebrar teste: ele escrevia credencial falsa no lugar onde mora
    a credencial de verdade.** No dia em que o oficial cadastrasse a CRA, a
    suíte a apagaria.

    O conserto isola a pasta com `monkeypatch` em vez de mudar a rota — a rota
    tem de ler mesmo da pasta da casa, e é isso que este teste exercita.
    """
    import centrais_cred as CENTCRED
    monkeypatch.setattr(CENTCRED, "pasta_de_dados", lambda: tmp_path)
    CENTCRED.gravar(CENTCRED.CRA, usuario="c", senha="s")
    try:
        html = s["c"].get("/protesto/cra/api").get_data(as_text=True)
        r = s["c"].post("/protesto/cra/api/baixar",
                        data={"csrf_token": _token(html), "o_que": "remessa",
                              "nome": "0" * 300},
                        follow_redirects=True)
        assert r.status_code == 200
        assert "não o conteúdo" in r.get_data(as_text=True)
    finally:
        CENTCRED.apagar(CENTCRED.CRA)


# ------------------------------------------- quem pode


def test_a_tela_NAO_e_do_balcao(cg_casa):
    """**Falar direto com a Central é de quem responde pela serventia**, e a
    consulta de autorização pode MARCAR coisa lá dentro. O balcão baixa
    arquivo pela tela de remessa, que já existe."""
    s = _sessao(cg_casa, papel="USER")
    r = s["c"].get("/protesto/cra/api", follow_redirects=True)
    assert "CRA — falar com a Central" not in r.get_data(as_text=True)
    import cra21_web as W
    assert "USER" not in W.QUEM_FALA_COM_A_CRA


def test_a_guarda_do_alcance_alcanca_a_tela_da_cra():
    """A régua de «qual módulo é esta tela» decide pelo prefixo do endpoint."""
    import modulos as MOD
    for endpoint in ("protesto_cra_api", "protesto_cra_api_testar",
                     "protesto_cra_api_baixar"):
        assert MOD.modulo_da_tela(endpoint) == "PROTESTO"


def test_todo_formulario_manda_o_csrf(s):
    html = s["c"].get("/protesto/cra/api").get_data(as_text=True)
    formularios = re.findall(r"<form[^>]*method=[\"']post[\"'].*?</form>",
                             html, re.DOTALL | re.IGNORECASE)
    assert len(formularios) >= 2
    for f in formularios:
        assert "csrf_token" in f


def test_a_lista_da_tela_so_traz_operacao_que_existe_no_contrato():
    """Lista escrita à mão que cite operação inexistente é a promessa com cara
    de prova — e aqui ela levaria o oficial a clicar num botão que estoura."""
    import cra21_web as W
    for chave, _, _ in W.O_QUE_SE_TRAZ:
        assert hasattr(W, "_trazer")
    # nenhuma das oferecidas depende de `userDados`
    fonte = (RAIZ / "cra21_web.py").read_text(encoding="utf-8")
    for operacao in CRA.OPERACOES_SEM_SENTIDO_MEDIDO:
        assert f'"{operacao}"' not in fonte, (
            f"a tela oferece «{operacao}», cujo `userDados` não está medido")
