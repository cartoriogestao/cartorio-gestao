"""A CERTIDÃO DE ÔNUS DO RI LEVA DOIS SELOS — decisão do oficial, 19/11/2026.

O balcão relatou que a certidão de ônus cobre duas certidões num papel só —
os ônus reais e as ações reais e pessoais reipersecutórias — e que o sistema
gerava um selo só, mesmo com dois itens lançados. A decisão: dois itens
16.24.4, dois selos, um papel e um número no livro de certidões.

Fundamento: Decreto 93.240/1986, art. 1º, IV; Código de Normas do TJMA
(«certidão de ônus e certidão de ações reais e pessoais reipersecutórias»).

O QUE ESTES TESTES GUARDAM, pela tela e com o caixa de verdade
(`test_fluxo_ri.casa`: o selador de bancada com `protocolo_pago=False`, o
protocolo aberto, pago e atendido pelas telas do balcão):

    1. dois 16.24.4 pagos → dois selos 16.24.4, referências `ri_certidoes:ID`
       e `ri_certidoes:ID:acoes`, os dois itens gastos, nada pago sem selo;
    2. um 16.24.4 pago só → o primeiro selo sai, o das ações fica esperando
       com o motivo certo, e o «Selar», depois de pagar, completa só ele;
    3. pedir de novo não vende selo a mais, completa ou incompleta;
    4. três folhas → os dois 16.24.4 e um 16.24.4.1 com quantidade 2;
    5. os outros tipos não mudam;
    6. cancelar a de ônus leva os dois selos ao cancelamento;
    7. a ONR continua como estava (pergunta 4.1, respondida pelo titular em
       19/11/2026: um selo para os tipos 6, 15, 19 e 20);
    8. a liberação do ADMIN para o ato cobre também o selo das ações, com as
       mesmas regras de um selo (titular, 19/11/2026); pedir de novo não vende
       um terceiro selo, e o selo adicional das Notas continua sem ela.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import ato_selado as AS  # noqa: E402
import certidao_folhas as CFOLHAS  # noqa: E402
from test_fluxo_ri import (  # noqa: E402,F401  (`casa` é a fixture)
    COMPRADORA, ESCREVENTE, SERVICO, _certidao, _clicar, _compra_e_venda,
    _ler, _pede_certidao, _token, _um, casa)

#: O formulário da certidão de ônus negativa, como o balcão o preenche.
ONUS = {"onus_formulario": "1", "resultado_onus": "negativa",
        "resultado_acoes": "negativa", "proprietario_conferido": "1"}


@pytest.fixture()
def folhas(monkeypatch):
    """Quantas folhas o papel conta. O teste diz; a estimativa do PDF não."""
    def contar(n: int) -> None:
        monkeypatch.setattr(CFOLHAS, "folhas_do_html_como_certidao",
                            lambda *_a, **_k: n)
    contar(1)
    return contar


def _selos(casa, certidao_id: int) -> list[dict]:
    """Os selos amarrados à certidão no razão, com o item que a etiqueta diz."""
    linhas = _ler(casa, """SELECT numero, referencia, texto, cancelado_em,
                                  motivo_cancelamento
                             FROM sd_selos WHERE tabela='ri_certidoes' AND ato_id=%s
                            ORDER BY id""", (certidao_id,))
    for s in linhas:
        achado = re.search(r"Ato: ([\d.]+)", s["texto"] or "")
        s["codigo"] = achado.group(1) if achado else None
    return linhas


def _por_referencia(casa, certidao_id: int) -> dict[str, dict]:
    return {s["referencia"]: s for s in _selos(casa, certidao_id)}


def _aguardando(casa, certidao_id: int) -> dict | None:
    return _um(casa, """SELECT * FROM cx_selo_aguardando
                         WHERE tabela='ri_certidoes' AND ato_id=%s""", (certidao_id,))


def _item(casa, cx: dict, codigo: str) -> list[dict]:
    return _ler(casa, """SELECT * FROM cx_protocolo_atos
                          WHERE protocolo_id=%s AND codigo_ato=%s ORDER BY id""",
                (cx["id"], codigo))


def _coberturas(casa, certidao_id: int) -> dict[str, dict]:
    return {c["referencia"]: c for c in _ler(
        casa, """SELECT referencia, situacao, forma, item_id, unidades_gastas
                   FROM cx_selo_coberturas
                  WHERE tabela='ri_certidoes' AND ato_id=%s""", (certidao_id,))}


def _pagar_mais(casa, cx: dict, codigo: str, quantidade: int = 1) -> None:
    """O balcão acrescenta o item no MESMO protocolo e recebe."""
    c = casa["balcao"]
    ficha = f"/caixa/protocolos/{cx['id']}"
    html = _clicar(c, ficha, f"{ficha}/itens", acao="acrescentar",
                   servico=str(SERVICO[codigo]), quantidade=str(quantidade))
    assert f"Item {codigo} acrescentado" in html, html[:600]
    html = _clicar(c, ficha, f"{ficha}/itens", acao="quitar_todos",
                   forma_pagamento="DINHEIRO")
    assert "quitado" in html, html[:600]


def _selar(casa, certidao_id: int, matricula_id: int) -> str:
    """O botão «Selar» da certidão, na ficha da matrícula."""
    c = casa["balcao"]
    token = _token(c.get(f"/registro-imoveis/{matricula_id}").get_data(as_text=True))
    r = c.post(f"/registro-imoveis/certidoes/{certidao_id}/selar",
               data={"csrf_token": token}, follow_redirects=True)
    return r.get_data(as_text=True)


# ------------------------------------------------------------------ 1


def test_com_dois_16_24_4_pagos_a_de_onus_sai_com_dois_selos(casa, folhas):
    f = _compra_e_venda(casa)
    cx = _pede_certidao(casa, itens=(("16.24.4", 2),))
    cert = _certidao(casa, f["matricula"], "ONUS", cx=cx, **ONUS)
    cid = int(cert["linha"]["id"])

    selos = _por_referencia(casa, cid)
    assert set(selos) == {f"ri_certidoes:{cid}", f"ri_certidoes:{cid}:acoes"}, selos
    onus, acoes = selos[f"ri_certidoes:{cid}"], selos[f"ri_certidoes:{cid}:acoes"]
    assert onus["codigo"] == acoes["codigo"] == "16.24.4"
    assert onus["numero"] != acoes["numero"], "dois selos, e não o mesmo duas vezes"
    # A coluna guarda o primeiro; o papel traz os dois, cada um com o seu valor.
    assert cert["linha"]["selo_texto"] in {onus["numero"], acoes["numero"]}
    for s in (onus, acoes):
        assert s["numero"] in cert["papel"], f"o selo {s['numero']} não saiu no papel"
    # OS DOIS ITENS GASTOS, cada selo com a sua unidade, e nada pago sem selo.
    (item,) = _item(casa, cx, "16.24.4")
    assert int(item["quantidade_usada"]) == 2 and item["usado_em"]
    cob = _coberturas(casa, cid)
    for ref in selos:
        assert cob[ref]["situacao"] == "CONFIRMADA", cob
        assert int(cob[ref]["unidades_gastas"]) == 1, cob
        assert int(cob[ref]["item_id"]) == int(item["id"])
    assert _aguardando(casa, cid) is None, "a certidão completa não espera selo"
    with casa["db"].connect() as con:
        assert not [a for a in AS.aguardando_cobertura(con)
                    if a["tabela"] == "ri_certidoes" and int(a["ato_id"]) == cid]


# ------------------------------------------------------------------ 2 e 3


def test_com_um_16_24_4_so_o_das_acoes_espera_e_o_selar_completa(casa, folhas):
    f = _compra_e_venda(casa)
    m = f["matricula"]
    cx = _pede_certidao(casa, itens=(("16.24.4", 1),))
    cert = _certidao(casa, m, "ONUS", cx=cx, **ONUS)
    cid = int(cert["linha"]["id"])

    # O PRIMEIRO SAI; O DAS AÇÕES FICA ESPERANDO O SEU ITEM — sem «SEM SELO»,
    # que levaria a cancelar a certidão e queimar o primeiro selo.
    antes = _por_referencia(casa, cid)
    assert set(antes) == {f"ri_certidoes:{cid}"}, antes
    assert antes[f"ri_certidoes:{cid}"]["codigo"] == "16.24.4"
    assert not cert["linha"]["cancelada"]
    assert "SEM SELO" not in cert["recado"]
    assert "falta o item 16.24.4 das ações reais e pessoais reipersecutórias" \
        in cert["recado"], cert["recado"][:1500]
    espera = _aguardando(casa, cid)
    assert espera and "ações" in espera["motivo"], espera
    # O item pago foi gasto UMA vez: ele não paga o segundo selo.
    (item,) = _item(casa, cx, "16.24.4")
    assert int(item["quantidade_usada"]) == 1
    # A ficha mostra o botão da certidão com selo incompleto.
    ficha = casa["balcao"].get(f"/registro-imoveis/{m['id']}").get_data(as_text=True)
    assert "Selo incompleto" in ficha
    assert f"/registro-imoveis/certidoes/{cid}/selar" in ficha
    links = re.findall(r'href="(/selo/cobertura[^"]*)"', ficha)
    assert links, "a ficha não trouxe o «Escolher o protocolo»"
    assert any("pedido=16.24.4:1" in l and f"ato_id={cid}&" in l for l in links), \
        f"com o primeiro selo saído, falta um 16.24.4: {links}"

    # 3a. PEDIR DE NOVO SEM PAGAR: o mesmo primeiro selo, nada a mais.
    html = _selar(casa, cid, m["id"])
    assert "ainda espera selo" in html, html[:1500]
    assert _por_referencia(casa, cid) == antes
    assert int(_item(casa, cx, "16.24.4")[0]["quantidade_usada"]) == 1

    # PAGO O SEGUNDO ITEM, O «SELAR» PEDE SÓ O QUE FALTA.
    _pagar_mais(casa, cx, "16.24.4")
    html = _selar(casa, cid, m["id"])
    depois = _por_referencia(casa, cid)
    assert set(depois) == {f"ri_certidoes:{cid}", f"ri_certidoes:{cid}:acoes"}, html[:1500]
    assert depois[f"ri_certidoes:{cid}"]["numero"] == \
        antes[f"ri_certidoes:{cid}"]["numero"], "o primeiro selo não se compra de novo"
    assert depois[f"ri_certidoes:{cid}:acoes"]["codigo"] == "16.24.4"
    assert _aguardando(casa, cid) is None
    assert sum(int(i["quantidade_usada"]) for i in _item(casa, cx, "16.24.4")) == 2
    cob = _coberturas(casa, cid)
    assert cob[f"ri_certidoes:{cid}"]["item_id"] != cob[f"ri_certidoes:{cid}:acoes"]["item_id"], \
        "cada selo com o seu item pago"

    # 3b. PEDIR DE NOVO A COMPLETA: a tela recusa, e nada se vende.
    html = _selar(casa, cid, m["id"])
    assert "já tem selo" in html, html[:1500]
    assert _por_referencia(casa, cid) == depois


def test_a_folha_acrescida_que_sai_depois_nao_tira_a_das_acoes_da_fila(casa, folhas):
    """O selo que SAI tira o ato da fila (`obter_selo`). O das ações falta
    antes da folha acrescida, que sai: a certidão tem de voltar à fila."""
    folhas(2)
    f = _compra_e_venda(casa)
    cx = _pede_certidao(casa, itens=(("16.24.4", 1), ("16.24.4.1", 1)))
    cert = _certidao(casa, f["matricula"], "ONUS", cx=cx, **ONUS)
    cid = int(cert["linha"]["id"])
    assert set(_por_referencia(casa, cid)) == {
        f"ri_certidoes:{cid}", f"ri_certidoes:{cid}:16.24.4.1"}
    espera = _aguardando(casa, cid)
    assert espera and "ações" in espera["motivo"], espera


# ------------------------------------------------------------------ 4


def test_com_tres_folhas_a_folha_acrescida_vai_uma_vez_pelo_papel(casa, folhas):
    """Pergunta 4.2 do plano T006, na proposta: o papel é um só."""
    folhas(3)
    f = _compra_e_venda(casa)
    cx = _pede_certidao(casa, itens=(("16.24.4", 2), ("16.24.4.1", 9)))
    cert = _certidao(casa, f["matricula"], "ONUS", cx=cx, **ONUS)
    cid = int(cert["linha"]["id"])
    selos = _por_referencia(casa, cid)
    assert {r: s["codigo"] for r, s in selos.items()} == {
        f"ri_certidoes:{cid}": "16.24.4",
        f"ri_certidoes:{cid}:acoes": "16.24.4",
        f"ri_certidoes:{cid}:16.24.4.1": "16.24.4.1"}
    assert int(_item(casa, cx, "16.24.4.1")[0]["quantidade_usada"]) == 2
    assert int(_item(casa, cx, "16.24.4")[0]["quantidade_usada"]) == 2
    assert _aguardando(casa, cid) is None


# ------------------------------------------------------------------ 5


@pytest.mark.parametrize("tipo, base", [
    ("INTEIRO_TEOR", "16.24.4"), ("PROPRIEDADE", "16.24.1"),
    ("DOMINIAL", "16.24.4"), ("VINTENARIA", "16.24.4")])
def test_os_outros_tipos_nao_mudam(tipo, base):
    acrescida = AS.ITEM_DA_FOLHA_ACRESCIDA_DO_RI[base]
    assert AS.itens_da_certidao_do_ri(tipo, 1) == [(base, 1)]
    assert AS.itens_da_certidao_do_ri(tipo, 3) == [(base, 1), (acrescida, 2)]
    selos = AS.selos_da_certidao_do_ri(7, AS.itens_da_certidao_do_ri(tipo, 3))
    assert [s["referencia"] for s in selos] == ["ri_certidoes:7",
                                                f"ri_certidoes:7:{acrescida}"]
    assert not any(s["acoes"] for s in selos)
    assert tipo not in AS.TIPOS_DO_RI_COM_DOIS_SELOS


def test_o_inteiro_teor_pela_tela_continua_com_um_selo(casa, folhas):
    f = _compra_e_venda(casa)
    cx = _pede_certidao(casa, itens=(("16.24.4", 1),))
    cert = _certidao(casa, f["matricula"], "INTEIRO_TEOR", cx=cx)
    cid = int(cert["linha"]["id"])
    assert set(_por_referencia(casa, cid)) == {f"ri_certidoes:{cid}"}
    assert _aguardando(casa, cid) is None


# ------------------------------------------------------------------ 6


def test_cancelar_a_de_onus_cancela_os_dois_selos(casa, folhas):
    f = _compra_e_venda(casa)
    m = f["matricula"]
    cx = _pede_certidao(casa, itens=(("16.24.4", 2),))
    cert = _certidao(casa, m, "ONUS", cx=cx, **ONUS)
    cid = int(cert["linha"]["id"])
    assert len(_selos(casa, cid)) == 2
    motivo = "Emitida para a matrícula errada, a pedido do requerente"
    html = _clicar(casa["oficial"], f"/registro-imoveis/{m['id']}",
                   f"/registro-imoveis/certidoes/{cid}/cancelar",
                   motivo=motivo, selo_cancelado_tjma="1", voltar="ficha")
    assert "Certidão cancelada" in html, html[:1500]
    selos = _selos(casa, cid)
    assert len(selos) == 2
    for s in selos:
        assert s["cancelado_em"], f"o selo {s['referencia']} não entrou no cancelamento"
        assert s["motivo_cancelamento"] == motivo


# ------------------------------------------------------------------ 7


def test_a_onr_continua_com_um_item_ate_a_pergunta_4_1(casa):
    """Os tipos 19 (só ações) e 20 (só ônus) da ONR também viram `ONUS`; até
    o oficial decidir, a certidão digital da ONR fica como estava."""
    import onr_certidoes_auto as AUTO
    assert AS.itens_da_certidao_do_ri("ONUS", 5, digital=True) == [("16.24.4", 1)]
    assert [s["referencia"] for s in AS.selos_da_certidao_do_ri(
        9, AS.itens_da_certidao_do_ri("ONUS", 5, digital=True))] == ["ri_certidoes:9"]
    assert AUTO.TIPOS_ONR_DE_ONUS == {"6", "15", "19", "20"}
    for tipo_onr in AUTO.TIPOS_ONR_DE_ONUS:
        assert AUTO.sugerir(None, {"tipo_certidao": tipo_onr, "pesquisa_por": "matricula",
                                   "matricula_id": 1})["tipo_ri"] == "ONUS"
    # O «Escolher o protocolo» da certidão sem selo pede o que a regra pede.
    quantos = casa["app"].jinja_env.globals["itens_base_da_certidao"]
    assert quantos({"tipo": "ONUS", "finalidade": "Para fins de financiamento"}) == 2
    assert quantos({"tipo": "ONUS", "finalidade": AS.PREFIXO_DA_FINALIDADE_ONR + "X1"}) == 1
    assert quantos({"tipo": "INTEIRO_TEOR", "finalidade": None}) == 1
    with casa["db"].connect() as con:
        onus = AUTO.custas_pela_tabela(con, "ONUS", folhas=4)
        inteiro = AUTO.custas_pela_tabela(con, "INTEIRO_TEOR", folhas=4)
    assert onus and onus == inteiro, "a ONR cobra o mesmo 16.24.4, uma vez"


def test_com_a_trava_desligada_o_das_acoes_sai_como_os_outros(casa, folhas):
    """`item_proprio` só separa o item quando a trava está valendo: desligada,
    nenhum selo do ato confere item, e o das ações não pode ficar esperando."""
    casa["db"].set_settings({AS.CHAVE_DA_TRAVA: AS.TRAVA_DESLIGADA})
    f = _compra_e_venda(casa)
    cert = _certidao(casa, f["matricula"], "ONUS", cx={"numero": ""},
                     **ONUS)
    cid = int(cert["linha"]["id"])
    assert set(_por_referencia(casa, cid)) == {f"ri_certidoes:{cid}",
                                               f"ri_certidoes:{cid}:acoes"}
    assert {c["forma"] for c in _coberturas(casa, cid).values()} == {"TRAVA_DESLIGADA"}
    assert _aguardando(casa, cid) is None


# ------------------------------------------------------------------ 8


#: A justificativa do ADMIN, como a tela pede: uma frase que diga algo.
JUSTIFICATIVA = "Cliente volta amanhã para pagar; o oficial autorizou a entrega."


def _liberar(casa, certidao_id: int) -> str:
    """«Liberar selo sem cobertura», do ADMIN, na tela da cobertura do ato."""
    tela = f"/selo/cobertura?tabela=ri_certidoes&ato_id={certidao_id}"
    return _clicar(casa["oficial"], tela, "/selo/cobertura/liberar",
                   tabela="ri_certidoes", ato_id=str(certidao_id),
                   justificativa=JUSTIFICATIVA)


def _onus_sem_pagamento(casa, matricula: dict) -> int:
    """A certidão de ônus emitida sem protocolo pago. Sem selo, o papel não
    se imprime — por isso não se pede o .odt, como `_certidao` faz."""
    c = casa["balcao"]
    ficha = f"/registro-imoveis/{matricula['id']}"
    token = _token(c.get(ficha).get_data(as_text=True))
    r = c.post(f"{ficha}/certidao", data={
        "csrf_token": token, "tipo": "ONUS", "fonte_corpo": "TEXTO", "folhas": "",
        "requerente": COMPRADORA["nome"],
        "requerente_documento": COMPRADORA["cpf_fmt"],
        "finalidade": "Para fins de financiamento", "emolumentos": "",
        "protocolo": "", "busca_formulario": "1", "busca_item": "16.25.9", **ONUS})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    linha = _um(casa, "SELECT * FROM ri_certidoes ORDER BY id DESC LIMIT 1")
    assert linha["tipo"] == "ONUS" and not linha["cancelada"], linha
    return int(linha["id"])


def _liberacoes(casa, certidao_id: int) -> list[dict]:
    return _ler(casa, """SELECT * FROM cx_selo_liberacoes
                          WHERE tabela='ri_certidoes' AND ato_id=%s""", (certidao_id,))


def test_a_liberacao_do_admin_cobre_tambem_o_selo_das_acoes(casa, folhas):
    """Titular, 19/11/2026: «as regras que já existem para 1 selo deve manter
    para 2». A liberação é do ATO: a mesma, com o mesmo perfil, a mesma
    justificativa e a mesma auditoria, cobre o selo das ações."""
    f = _compra_e_venda(casa)
    m = f["matricula"]
    cx = _pede_certidao(casa, itens=(("16.24.4", 1),))
    cert = _certidao(casa, m, "ONUS", cx=cx, **ONUS)
    cid = int(cert["linha"]["id"])
    antes = _por_referencia(casa, cid)
    assert set(antes) == {f"ri_certidoes:{cid}"}

    # SEM A LIBERAÇÃO, COMO HOJE: o das ações continua esperando o seu item.
    html = _selar(casa, cid, m["id"])
    assert "ainda espera selo" in html, html[:1500]
    assert _por_referencia(casa, cid) == antes

    # O ESCREVENTE NÃO LIBERA — a regra de um selo, sem permissão nova.
    c = casa["balcao"]
    tela = f"/selo/cobertura?tabela=ri_certidoes&ato_id={cid}"
    token = _token(c.get(f"/registro-imoveis/{m['id']}").get_data(as_text=True))
    r = c.post("/selo/cobertura/liberar", data={
        "csrf_token": token, "tabela": "ri_certidoes", "ato_id": str(cid),
        "justificativa": JUSTIFICATIVA})
    assert r.status_code in (302, 403), r.status_code
    assert not _liberacoes(casa, cid), "o escrevente liberou o selo"
    assert tela  # a mesma tela que o ADMIN usa, abaixo

    # O ADMIN LIBERA, E O «SELAR» SOLTA O DAS AÇÕES, sem gastar item.
    assert "Selo liberado" in _liberar(casa, cid)
    html = _selar(casa, cid, m["id"])
    depois = _por_referencia(casa, cid)
    assert set(depois) == {f"ri_certidoes:{cid}", f"ri_certidoes:{cid}:acoes"}, html[:1500]
    assert depois[f"ri_certidoes:{cid}"]["numero"] == antes[f"ri_certidoes:{cid}"]["numero"]
    assert depois[f"ri_certidoes:{cid}:acoes"]["codigo"] == "16.24.4"
    cob = _coberturas(casa, cid)
    assert cob[f"ri_certidoes:{cid}:acoes"]["forma"] == AS.FORMA_LIBERADO, cob
    assert cob[f"ri_certidoes:{cid}:acoes"]["situacao"] == "CONFIRMADA", cob
    assert cob[f"ri_certidoes:{cid}"]["forma"] != AS.FORMA_LIBERADO, \
        "o primeiro continua pago pelo item"
    assert int(_item(casa, cx, "16.24.4")[0]["quantidade_usada"]) == 1
    assert _aguardando(casa, cid) is None
    (lib,) = _liberacoes(casa, cid)
    assert lib["justificativa"] == JUSTIFICATIVA and lib["usado_em"]

    # PEDIR DE NOVO NÃO VENDE UM TERCEIRO SELO.
    html = _selar(casa, cid, m["id"])
    assert "já tem selo" in html, html[:1500]
    assert _por_referencia(casa, cid) == depois
    assert len(_selos(casa, cid)) == 2


def test_sem_pagamento_a_liberacao_solta_os_dois_selos(casa, folhas):
    """Sem item pago nenhum, a certidão espera o selo. Liberada, os dois saem
    pela liberação, e o ato fica na lista dos liberados sem cobertura com os
    dois números — a pendência de pagamento continua, como num selo só."""
    f = _compra_e_venda(casa)
    m = f["matricula"]
    cid = _onus_sem_pagamento(casa, m)
    assert _selos(casa, cid) == [], "sem pagamento não sai selo nenhum"
    assert _aguardando(casa, cid)

    assert "Selo liberado" in _liberar(casa, cid)
    html = _selar(casa, cid, m["id"])
    selos = _por_referencia(casa, cid)
    assert set(selos) == {f"ri_certidoes:{cid}", f"ri_certidoes:{cid}:acoes"}, html[:1500]
    assert {c["forma"] for c in _coberturas(casa, cid).values()} == {AS.FORMA_LIBERADO}
    assert _aguardando(casa, cid) is None
    with casa["db"].connect() as con:
        pendentes = [l for l in AS.liberados_sem_cobertura(con)
                     if l["tabela"] == "ri_certidoes" and int(l["ato_id"]) == cid]
    assert len(pendentes) == 1
    assert set(pendentes[0]["selos"]) == {s["numero"] for s in selos.values()}

    html = _selar(casa, cid, m["id"])
    assert "já tem selo" in html, html[:1500]
    assert len(_selos(casa, cid)) == 2, "pedir de novo vendeu um terceiro selo"


def test_o_selo_adicional_das_notas_continua_sem_a_liberacao(casa, folhas, monkeypatch):
    """Só o selo das ações recebe a liberação; o adicional das Notas, não
    (12/11/2026: cobriria o 2º selo com a liberação do 1º)."""
    f = _compra_e_venda(casa)
    cid = _onus_sem_pagamento(casa, f["matricula"])
    assert "Selo liberado" in _liberar(casa, cid)

    # NO DOMÍNIO: com o item próprio e sem `liberacao_cobre`, a liberação do
    # ato não cobre; com ela, cobre. A transação volta: nada fica gravado.
    class _Volta(Exception):
        pass
    for cobre, esperado in ((False, False), (True, True)):
        try:
            with casa["db"].transaction() as con:
                r = AS.cobrir_o_selo(
                    con, tabela="ri_certidoes", ato_id=cid,
                    referencia=f"ri_certidoes:{cid}:teste", dados={},
                    usuario=ESCREVENTE["nome"], agora="2026-11-19T10:00:00",
                    item_proprio=True, liberacao_cobre=cobre)
                assert bool(r["coberto"]) is esperado, (cobre, r)
                raise _Volta
        except _Volta:
            pass

    # EM `obter_selo`: o selo adicional pede sem a liberação; o das ações, com.
    vistos = []
    def espiar(con, **kw):
        vistos.append((kw["item_proprio"], kw["liberacao_cobre"]))
        return {"coberto": False, "quadro": {}, "faltam": []}
    monkeypatch.setattr(AS, "cobrir_o_selo", espiar)
    for extra in ({"selo_adicional": True}, {"item_proprio": True}):
        with pytest.raises(Exception):
            AS.obter_selo(casa["db"], casa["app"].config["DATA_DIR"],
                          caminho="/selo/imovel/certidao", dados={},
                          referencia=f"ri_certidoes:{cid}:x", atribuicao="IMOVEL",
                          agora="2026-11-19T10:00:00", cns="",
                          usuario=ESCREVENTE["nome"], tabela="ri_certidoes",
                          ato_id=cid, **extra)
    assert vistos == [(True, False), (True, True)], vistos
