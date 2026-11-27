"""«UMA LINHA COM N» OU «N LINHAS DE 1, UMA PARA CADA ATO» — T023, 27/11/2026.

O PEDIDO DA OPERADORA, com vídeo: ela lança no protocolo um item com
quantidade maior que 1 e, ao lavrar, só um ato recebe o item. O mesmo
«item × N» quer dizer coisas diferentes conforme a atribuição:

- no RI (saldo por unidade, `caixa_protocolo.itens_disponiveis`), N atos, cada
  um gastando uma unidade;
- nas atribuições de folhas (RTD, RCPJ, Protesto, certidões —
  `atribuicoes_web._itens_para_selar`, regra do oficial de 11/09/2026), UM ato
  com N folhas: o primeiro ato marca a linha inteira, e o segundo não a acha;
- na autenticação de cópia (13.18), N selos.

Uma linha de quantidade 1 funciona igual em todas as telas de lavrar. Por isso
o balcão passa a escolher, ao acrescentar, entre «uma linha com N» (o padrão,
como sempre) e «N linhas de 1». NENHUMA REGRA MUDA: com «uma linha com N» tudo
segue como antes, e a divisão é recusada quando mudaria o total ou
contrariaria a regra do item (decisões do titular, 27/11/2026).

Dados fictícios (LGPD): nomes «DE EXEMPLO» e os documentos dos fictícios.
"""
from __future__ import annotations

import html as HTML
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import caixa_protocolo as CXP  # noqa: E402
import emolumentos as EMOL  # noqa: E402
from bd_nativo import banco  # noqa: E402
from caixa_schema import centavos, reais  # noqa: E402

SENHA = "Senha#12345"
VIGENCIA = 10022
REAIS = json.loads((RAIZ / "tests" / "custas_reais.json").read_text("utf-8"))
TABELA = {e["tj"]: e for e in REAIS["valores_2026"]}
# Os itens da tabela real de 2026 que os testes usam, e um fictício com o teto
# escrito na descrição inteira (a tabela importada do E-Ofício a traz cortada).
ITENS = ("15.3.1", "13.18", "16.24.4", "16.24.4.1", "16.5", "16.22.2")
TETO_NA_DESCRICAO = {"s": 990001, "tj": "99.1",
                     "descricao": "Ato de exemplo, por unidade, limitado ao valor máximo de dez",
                     "emol": 10.0, "ferc": 0.3, "femp": 0.4, "fadp": 0.4, "ferrfis": 0.1}
CAMPOS = ("emolumentos", "ferc", "fadep", "femp", "ferrfis", "valor_total")


# ------------------------------------------------------------------ o preparo


def _cent(v: float) -> int:
    return int(round(float(v) * 100))


def _semear(db) -> None:
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever(
            """INSERT INTO cx_vigencias (codigo, descricao, vigente, importado_em)
               VALUES (%s, '2026', 1, '2026-08-21') ON CONFLICT DO NOTHING""",
            (VIGENCIA,))
        for e in [TABELA[tj] for tj in ITENS] + [TETO_NA_DESCRICAO]:
            fundos = [_cent(e[k]) for k in ("emol", "ferc", "femp", "fadp", "ferrfis")]
            bd.escrever(
                """INSERT INTO cx_servicos (codigo, codigo_tj, descricao, ativo)
                   VALUES (%s, %s, %s, 1) ON CONFLICT DO NOTHING""",
                (int(e["s"]), e["tj"], e["descricao"]))
            bd.escrever(
                """INSERT INTO cx_servico_valores (servico, vigencia, emolumentos,
                       ferc, femp, fadep, ferrfis, total)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (int(e["s"]), VIGENCIA, *[reais(f) for f in fundos], reais(sum(fundos))))


def _servico(tj: str) -> str:
    return str(TETO_NA_DESCRICAO["s"] if tj == TETO_NA_DESCRICAO["tj"]
               else int(TABELA[tj]["s"]))


@pytest.fixture()
def casa(cg_casa_logada):
    _semear(cg_casa_logada["db"])
    return cg_casa_logada


def _token(c, url: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                       c.get(url).get_data(as_text=True))
    assert achado, f"{url} não trouxe csrf_token"
    return achado.group(1)


def _avisos(html: str) -> str:
    return " | ".join(
        HTML.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", x))).strip()
        for x in re.findall(r'class="flash[^"]*"[^>]*>(.*?)</', html, re.S))


def _novo_protocolo(casa, atribuicao: str = "RTD") -> int:
    c = casa["c"]
    r = c.post("/caixa/protocolos", data={
        "csrf_token": _token(c, "/caixa/protocolos"), "acao": "novo",
        "interessado": "FULANA DE EXEMPLO", "telefone": "(99) 0000-0000",
        "atribuicao": atribuicao, "assunto": "Pedido de exemplo"})
    assert r.status_code == 302, r.status_code
    return int(r.headers["Location"].rstrip("/").split("/")[-1])


def _acrescentar(casa, pid: int, **campos) -> str:
    c = casa["c"]
    ficha = f"/caixa/protocolos/{pid}"
    r = c.post(f"{ficha}/itens", data={"csrf_token": _token(c, ficha),
                                       "acao": "acrescentar", **campos},
               follow_redirects=True)
    return _avisos(r.get_data(as_text=True))


def _linhas(casa, pid: int) -> list[dict]:
    with casa["db"].connect() as con:
        return [dict(r) for r in banco(con).ler(
            "SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s ORDER BY id", (pid,))]


def _auditorias(casa, pid: int) -> list[dict]:
    with casa["db"].connect() as con:
        linhas = banco(con).ler(
            """SELECT details FROM audit_logs WHERE action='PROTOCOLO_ITEM_ACRESCENTADO'
                AND entity_type='PROTOCOLO' AND entity_id=%s ORDER BY id""", (pid,))
    return [json.loads(r["details"]) if isinstance(r["details"], str) else dict(r["details"])
            for r in linhas]


def _soma(linhas: list[dict]) -> dict:
    return {c: sum(centavos(x[c]) for x in linhas) for c in CAMPOS}


def _sem_ids(linha: dict) -> dict:
    return {k: v for k, v in linha.items()
            if k not in ("id", "protocolo_id", "criado_em", "created_at", "atualizado_em")}


# ------------------------------------------------------- a divisão que vale


def test_tres_linhas_de_1_somam_o_mesmo_que_uma_linha_com_3(casa):
    """Item de valor fixo, sem teto: três linhas de quantidade 1, o mesmo total
    e os mesmos fundos de «uma linha com 3», e uma auditoria só."""
    dividido, inteiro = _novo_protocolo(casa), _novo_protocolo(casa)
    aviso = _acrescentar(casa, dividido, servico=_servico("15.3.1"),
                         quantidade="3", separar="linhas")
    assert "Item 15.3.1 acrescentado em 3 linhas de 1" in aviso, aviso
    _acrescentar(casa, inteiro, servico=_servico("15.3.1"), quantidade="3",
                 separar="linha")
    linhas, uma = _linhas(casa, dividido), _linhas(casa, inteiro)
    assert [x["quantidade"] for x in linhas] == [1, 1, 1]
    assert {x["codigo_ato"] for x in linhas} == {"15.3.1"}
    assert len({json.dumps(_sem_ids(x), default=str, sort_keys=True)
                for x in linhas}) == 1, "as três linhas não são iguais"
    assert [x["quantidade"] for x in uma] == [3]
    assert _soma(linhas) == _soma(uma), "a divisão mudou o total ou um fundo"
    with casa["db"].connect() as con:
        totais = {r["id"]: r["valor_total"] for r in banco(con).ler(
            "SELECT id, valor_total FROM cx_protocolos WHERE id IN (%s, %s)",
            (dividido, inteiro))}
    assert centavos(totais[dividido]) == centavos(totais[inteiro]) > 0
    auditorias = _auditorias(casa, dividido)
    assert len(auditorias) == 1
    assert auditorias[0]["separado_em"] == 3
    assert auditorias[0]["codigo_tj"] == "15.3.1"


def test_uma_linha_com_3_continua_igual_a_hoje(casa):
    """«Uma linha com N» é o de sempre, byte a byte: marcada ou sem o campo
    (o formulário de antes), sai a mesma linha e a mesma auditoria."""
    marcada, sem_campo = _novo_protocolo(casa), _novo_protocolo(casa)
    _acrescentar(casa, marcada, servico=_servico("15.3.1"), quantidade="3",
                 separar="linha")
    _acrescentar(casa, sem_campo, servico=_servico("15.3.1"), quantidade="3")
    a, b = _linhas(casa, marcada), _linhas(casa, sem_campo)
    assert len(a) == len(b) == 1 and a[0]["quantidade"] == 3
    assert _sem_ids(a[0]) == _sem_ids(b[0])
    assert _auditorias(casa, marcada) == _auditorias(casa, sem_campo)
    assert "separado_em" not in _auditorias(casa, marcada)[0]


def test_quantidade_1_com_linhas_e_uma_linha_so(casa):
    pid = _novo_protocolo(casa)
    _acrescentar(casa, pid, servico=_servico("15.3.1"), quantidade="1",
                 separar="linhas")
    assert [x["quantidade"] for x in _linhas(casa, pid)] == [1]
    assert "separado_em" not in _auditorias(casa, pid)[0]


def test_cinquenta_linhas_e_o_limite(casa):
    pid = _novo_protocolo(casa)
    aviso = _acrescentar(casa, pid, servico=_servico("15.3.1"), quantidade="50",
                         separar="linhas")
    assert "acrescentado em 50 linhas de 1" in aviso, aviso
    assert len(_linhas(casa, pid)) == 50


# --------------------------------------------------- a divisão que se recusa


def _recusado(casa, aviso: str, pid: int, trecho: str) -> None:
    assert "Nada foi acrescentado" in aviso, aviso
    assert trecho in aviso, aviso
    assert _linhas(casa, pid) == [], "a divisão recusada gravou linha"
    assert _auditorias(casa, pid) == [], "a divisão recusada deixou auditoria"


def test_cinquenta_e_uma_linhas_e_recusado(casa):
    pid = _novo_protocolo(casa)
    aviso = _acrescentar(casa, pid, servico=_servico("15.3.1"), quantidade="51",
                         separar="linhas")
    _recusado(casa, aviso, pid, "até 50 linhas")
    assert "Lance uma linha com 51" in aviso


@pytest.mark.parametrize("tj", ["16.5", "99.1"], ids=["16.5", "teto-na-descricao"])
def test_item_com_teto_nao_se_divide(casa, tj):
    pid = _novo_protocolo(casa)
    aviso = _acrescentar(casa, pid, servico=_servico(tj), quantidade="3",
                         separar="linhas")
    _recusado(casa, aviso, pid, "tem teto")


def test_item_com_teto_que_a_conta_aplica_nao_se_divide(casa, monkeypatch):
    """A tabela fictícia em que 3 × 1 passa do teto de 3: o item de quantidade
    N sai limitado, e a soma das linhas de 1 seria maior. A conta é conferida
    fundo a fundo, e a divisão cai — mesmo sem a palavra «teto» na descrição."""
    calcular = EMOL.calcular_item

    def com_teto(con, *a, quantidade=1, **kw):
        # o teto é o de duas unidades: a terceira já não se cobra
        item = calcular(con, *a, quantidade=quantidade, **kw)
        if item and quantidade > 2:
            emol = centavos(item["emolumentos"])
            corte = emol - emol // quantidade * 2
            item = dict(item, emolumentos=reais(emol - corte),
                        total=reais(centavos(item["total"]) - corte))
        return item

    monkeypatch.setattr(EMOL, "calcular_item", com_teto)
    pid = _novo_protocolo(casa)
    aviso = _acrescentar(casa, pid, servico=_servico("15.3.1"), quantidade="3",
                         separar="linhas")
    _recusado(casa, aviso, pid, "o total mudaria")


def test_item_por_faixa_que_nao_fecha_e_recusado(casa, monkeypatch):
    """Item por faixa, com a base do negócio: quando 3 × (o de 1) não é o de 3,
    a divisão cai e nada se grava."""
    with casa["db"].transaction() as con:
        banco(con).escrever(
            """INSERT INTO cx_faixas (tabela, vigencia, de, ate, codigo_tj, emolumentos,
                   ferc, femp, fadep, ferrfis, total)
               VALUES (5, %s, '0,00', '999.999.999,99', '16.3.14', '100,00',
                       '3,00', '4,00', '4,00', '1,00', '112,00')""", (VIGENCIA,))
    calcular = EMOL.calcular_item

    def por_faixa(con, *a, quantidade=1, **kw):
        item = calcular(con, *a, quantidade=quantidade, **kw)
        if item and quantidade == 3:      # a faixa que, para três, cobra menos
            item = dict(item, ferc=reais(centavos(item["ferc"]) - 3),
                        total=reais(centavos(item["total"]) - 3))
        return item

    monkeypatch.setattr(EMOL, "calcular_item", por_faixa)
    pid = _novo_protocolo(casa, "RI")
    aviso = _acrescentar(casa, pid, tabela="5", base_calculo="100.000,00",
                         quantidade="3", separar="linhas")
    _recusado(casa, aviso, pid, "o total mudaria")


def test_item_por_faixa_que_fecha_divide(casa):
    """O passo 4 do plano: item com base divide quando a conta de 1 e de N
    fecha."""
    with casa["db"].transaction() as con:
        banco(con).escrever(
            """INSERT INTO cx_faixas (tabela, vigencia, de, ate, codigo_tj, emolumentos,
                   ferc, femp, fadep, ferrfis, total)
               VALUES (5, %s, '0,00', '999.999.999,99', '16.3.14', '100,00',
                       '3,00', '4,00', '4,00', '1,00', '112,00')""", (VIGENCIA,))
    pid = _novo_protocolo(casa, "RI")
    aviso = _acrescentar(casa, pid, tabela="5", base_calculo="100.000,00",
                         quantidade="3", separar="linhas")
    assert "acrescentado em 3 linhas de 1" in aviso, aviso
    linhas = _linhas(casa, pid)
    assert [(x["codigo_ato"], x["quantidade"], x["base_calculo"]) for x in linhas] == [
        ("16.3.14", 1, "100.000,00")] * 3
    assert _soma(linhas)["valor_total"] == 3 * 11200


def test_garantia_em_varios_imoveis_nao_se_divide(casa):
    """O 16.31: a quantidade já é multiplicada pelos imóveis."""
    with casa["db"].transaction() as con:
        banco(con).escrever(
            """INSERT INTO cx_faixas (tabela, vigencia, de, ate, codigo_tj, emolumentos,
                   ferc, femp, fadep, ferrfis, total)
               VALUES (5, %s, '0,00', '999.999.999,99', '16.3.14', '100,00',
                       '3,00', '4,00', '4,00', '1,00', '112,00')""", (VIGENCIA,))
    pid = _novo_protocolo(casa, "RI")
    aviso = _acrescentar(casa, pid, tabela="5", base_calculo="100.000,00",
                         imoveis="2", quantidade="3", separar="linhas")
    _recusado(casa, aviso, pid, "16.31")


@pytest.mark.parametrize("tj,trecho", [
    ("13.18", "autenticação de cópia"),
    ("16.24.4", "certidão do RI"),
    ("16.24.4.1", "folha acrescida"),
])
def test_item_com_regra_da_quantidade_nao_se_divide(casa, tj, trecho):
    """A autenticação (N no item são N selos), a certidão do RI (a de ônus com
    dois selos) e a folha acrescida (as folhas de uma certidão): a divisão
    contrariaria a regra, mesmo com o total igual."""
    pid = _novo_protocolo(casa)
    aviso = _acrescentar(casa, pid, servico=_servico(tj), quantidade="3",
                         separar="linhas")
    _recusado(casa, aviso, pid, trecho)


def test_protocolo_encerrado_recusa_como_hoje(casa):
    pid = _novo_protocolo(casa)
    c, ficha = casa["c"], f"/caixa/protocolos/{pid}"
    r = c.post(ficha, data={"csrf_token": _token(c, ficha), "acao": "encerrar",
                            "encerramento": CXP.CANCELADO,
                            "motivo": "O cliente de exemplo desistiu do pedido."},
               follow_redirects=True)
    assert "encerrado" in _avisos(r.get_data(as_text=True)).lower()
    aviso = _acrescentar(casa, pid, servico=_servico("15.3.1"), quantidade="3",
                         separar="linhas")
    assert "está encerrado" in aviso and "Nada foi alterado" in aviso, aviso
    assert _linhas(casa, pid) == []


def test_as_regras_de_antes_continuam_antes_da_divisao(casa):
    """A quantidade que não cabe na coluna `integer` cai como sempre caiu,
    antes de qualquer divisão."""
    pid = _novo_protocolo(casa)
    aviso = _acrescentar(casa, pid, servico=_servico("15.3.1"),
                         quantidade="9" * 30, separar="linhas")
    assert "numero inteiro" in aviso, aviso
    assert _linhas(casa, pid) == []


# ----------------------------------------------------------------- a regra


def _item(codigo: str, quantidade: int, **mais) -> dict:
    um = {"codigo_tj": codigo, "origem_valor": "TABELA", "quantidade": quantidade,
          "imoveis": 1, "descricao": "Ato de exemplo"}
    for campo, valor in (("emolumentos", 1000), ("ferc", 30), ("fadep", 40),
                         ("femp", 40), ("ferrfis", 10), ("total", 1120)):
        um[campo] = reais(valor * quantidade)
    return um | mais


def test_a_regra_sozinha():
    assert CXP.por_que_nao_dividir(_item("15.3.1", 1), _item("15.3.1", 3), 3) is None
    assert "até 50" in CXP.por_que_nao_dividir(_item("15.3.1", 1), _item("15.3.1", 51), 51)
    assert "faixa de um item do tribunal" in CXP.por_que_nao_dividir(
        _item("17.1.7", 1), _item("17.1.7", 3), 3)
    assert "faixa de um item do tribunal" in CXP.por_que_nao_dividir(
        _item("16.45.20", 1, origem_valor="FAIXA"),
        _item("16.45.20", 3, origem_valor="FAIXA"), 3)
    assert "metade da base" in CXP.por_que_nao_dividir(
        _item("16.22.4.1", 1, origem_valor="FAIXA_METADE_16.9"),
        _item("16.22.4.1", 3, origem_valor="FAIXA_METADE_16.9"), 3)
    assert "teto" in CXP.por_que_nao_dividir(
        _item("16.3.36", 1, origem_valor="FAIXA", acima_do_teto=True),
        _item("16.3.36", 3, origem_valor="FAIXA", acima_do_teto=True), 3)
    # «arquitetônico» não é teto: a palavra se procura inteira
    assert CXP.por_que_nao_dividir(
        _item("15.3.1", 1, descricao="Projeto arquitetônico"),
        _item("15.3.1", 3, descricao="Projeto arquitetônico"), 3) is None
    diferente = _item("15.3.1", 3)
    diferente["fadep"] = reais(119)
    assert "o total mudaria" in CXP.por_que_nao_dividir(_item("15.3.1", 1), diferente, 3)


def test_a_lista_das_folhas_acrescidas_e_a_do_sistema():
    """A lista de quem não se divide não se desencontra das regras de onde
    ela saiu."""
    import ato_selado as AS
    import notas_certidao as NC
    nao = CXP.ITENS_QUE_NAO_SE_DIVIDEM
    for folha in AS.ITEM_DA_FOLHA_ACRESCIDA_DO_RI.values():
        assert folha in nao, folha
    assert NC.ITEM_FOLHA_ACRESCIDA in nao
    assert "14.5.2" in EMOL.CODIGOS_ALIAS_CERTIDAO_RCPN and "14.5.2" in nao
    assert "13.18" in nao          # atribuicoes_web.CODIGO_TJ_AUTENTICACAO_COPIA
    assert CXP.LIMITE_DE_LINHAS_DA_DIVISAO == 50


# ------------------------------------------------------------------ a tela


def test_a_tela_mostra_a_escolha_na_faixa_e_nas_linhas_da_busca(casa):
    pid = _novo_protocolo(casa)
    html = casa["c"].get(f"/caixa/protocolos/{pid}?busca_ato=15.3.1").get_data(as_text=True)
    assert "separar_linhas.js" in html, "o script da escolha não é carregado"
    formularios = re.findall(r'<form method="post"[^>]*/itens"[^>]*>(.*?)</form>', html, re.S)
    com_quantidade = [f for f in formularios if 'name="quantidade"' in f]
    assert len(com_quantidade) >= 2, "faltou o formulário da faixa ou a linha da busca"
    for f in com_quantidade:
        assert "data-separar" in f, "um formulário com quantidade não traz a escolha"
        assert re.search(r'name="separar" value="linha" checked', f), (
            "«uma linha com N» não vem marcada")
        assert 'name="separar" value="linhas"' in f
        assert "linhas de 1" in f
    faixa = [f for f in com_quantidade if "Acrescentar pela faixa" in f]
    busca = [f for f in com_quantidade if 'name="servico"' in f]
    assert faixa and busca
    # o fragmento da busca enquanto se digita é a mesma macro
    pedaco = casa["c"].get(f"/caixa/protocolos/{pid}/atos-da-tabela?busca=15.3.1")
    assert pedaco.status_code == 200
    texto = pedaco.get_data(as_text=True)
    assert 'name="separar" value="linha" checked' in texto
    assert 'name="separar" value="linhas"' in texto


# ------------------------------------- de ponta a ponta: RTD, um ato por linha


from test_fluxo_rtd_rcpj import (Balcao, _avisos as _avisos_rtd,  # noqa: E402
                                 _token as _token_rtd, casa as casa_rtd)
from navegador_de_teste import postar_e_seguir  # noqa: E402

CNPJ = "00000043000177"


def test_rtd_tres_linhas_de_1_tres_registros_cada_um_com_a_sua(casa_rtd):
    """Três registros de RTD pagos num protocolo só, com «3 linhas de 1»: cada
    registro marca a sua linha, sai com o seu selo, e nada sobra. Com «uma
    linha com 3», o primeiro levaria a linha inteira (as folhas de um ato)."""
    b = Balcao(casa_rtd)
    b.abrir_caixa()
    titulos = [b.receber_titulo(4, serie="TD_B", natureza="Contrato de exemplo",
                                apresentante="EMPRESA DE EXEMPLO LTDA", documento=CNPJ)
               for _ in range(3)]
    pid = titulos[0]["protocolo_geral_id"]
    url = f"/caixa/protocolos/{pid}"
    servico = str(int(TABELA["15.3.1"]["s"]))
    r = b.post(f"{url}/itens", url, acao="acrescentar", servico=servico,
               quantidade="3", separar="linhas")
    assert "acrescentado em 3 linhas de 1" in _avisos_rtd(r), _avisos_rtd(r)
    r = b.post(f"{url}/itens", url, acao="quitar_todos", forma_pagamento="DINHEIRO")
    assert "lançado" in _avisos_rtd(r), _avisos_rtd(r)
    numero = b.um("SELECT numero FROM cx_protocolos WHERE id=%s", (pid,))["numero"]
    r = b.post("/selo/cobertura/atender", "/caixa", protocolo=numero)
    assert "atendendo o protocolo" in _avisos_rtd(r), _avisos_rtd(r)
    linhas = [x["id"] for x in b.ler(
        "SELECT id FROM cx_protocolo_atos WHERE protocolo_id=%s ORDER BY id", (pid,))]
    assert len(linhas) == 3
    atos = []
    for titulo, linha in zip(titulos, linhas):
        b.qualificar(titulo["id"], resultado="POSITIVA")
        tela = f"/rcpj-rtd/titulo/{titulo['id']}"
        postar_e_seguir(b.c, f"{tela}/registrar", {
            "csrf_token": _token_rtd(b.c, tela), "serie": "TD_B",
            "teor": f"CONTRATO DE EXEMPLO {linha}.", "protocolo_id": str(pid),
            "protocolo_item_id": [str(linha)]})
        atos.append(b.um("SELECT * FROM rg_atos ORDER BY id DESC LIMIT 1")["id"])
    assert len(set(atos)) == 3, "não saíram três registros"
    for ato in atos:
        selos = b.ler("SELECT referencia FROM sd_selos WHERE tabela='rg_atos' AND ato_id=%s",
                      (ato,))
        assert [s["referencia"].split(":")[-1] for s in selos] == ["15.3.1"], selos
    usados = b.ler("""SELECT id, usado_em, usado_por_ato_id FROM cx_protocolo_atos
                       WHERE protocolo_id=%s ORDER BY id""", (pid,))
    assert all(u["usado_em"] for u in usados), "sobrou linha sem ato"
    assert [u["usado_por_ato_id"] for u in usados] == atos, "uma linha foi para outro ato"
    assert b.um("SELECT count(*) AS n FROM sd_selos WHERE referencia LIKE %s",
                ("%:15.3.1",))["n"] == 3


# --------------------------------------- de ponta a ponta: RI, três averbações


from test_fluxo_ri import (PRIMEIRA_MATRICULA, SERVICO, VENDEDOR,  # noqa: E402
                           _abrir_o_caixa_do_dia, _clicar, _compra_e_venda, _lavrar,
                           _ler, _prenotar, _protocolo_geral, _um, casa as casa_ri)


def test_ri_tres_linhas_de_1_tres_averbacoes(casa_ri):
    """No RI, «3 linhas de 1» do 16.22.2 e três averbações na matrícula, cada
    uma marcando a sua linha: três selos, e as três linhas consumidas."""
    f = _compra_e_venda(casa_ri)
    m = f["matricula"]
    cx = _protocolo_geral(casa_ri, interessado=VENDEDOR, itens=[("16.1", 1)], pagar=False)
    c = casa_ri["balcao"]
    ficha_cx = f"/caixa/protocolos/{cx['id']}"
    html = _clicar(c, ficha_cx, f"{ficha_cx}/itens", acao="acrescentar",
                   servico=str(SERVICO["16.22.2"]), quantidade="3", separar="linhas")
    assert "acrescentado em 3 linhas de 1" in html, html[:600]
    if not _um(casa_ri, "SELECT id FROM cx_caixas WHERE situacao='ABERTO' "
                        "AND operador_nome='CARLA EXEMPLO' LIMIT 1"):
        _abrir_o_caixa_do_dia(c)
    html = _clicar(c, ficha_cx, f"{ficha_cx}/itens", acao="quitar_todos",
                   forma_pagamento="DINHEIRO")
    assert "quitado" in html, html[:600]
    p = _prenotar(casa_ri, cx, apresentante=VENDEDOR, natureza="Averbação de construção",
                  objeto=f"Matrícula {PRIMEIRA_MATRICULA}", matricula=str(PRIMEIRA_MATRICULA))
    linhas = [x["id"] for x in _ler(casa_ri, """SELECT id FROM cx_protocolo_atos
                                                 WHERE protocolo_id=%s AND codigo_ato='16.22.2'
                                                 ORDER BY id""", (cx["id"],))]
    assert len(linhas) == 3
    atos = []
    for i, linha in enumerate(linhas):
        html = _lavrar(casa_ri, m, tipo="AV", natureza="Construção",
                       teor=(f"AVERBAÇÃO DE CONSTRUÇÃO número {i + 1} de exemplo, com "
                             "80,00 m² na Rua Exemplo, 30."),
                       prenotacao=p if i == 0 else None, cx=cx, itens=[],
                       protocolo_item_id=[str(linha)])
        ato = _um(casa_ri, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC "
                           "LIMIT 1", (m["id"],))
        assert ato["id"] not in atos, f"a averbação {i + 1} não foi lavrada: {html[:900]}"
        assert ato["selo_texto"], f"a averbação {i + 1} saiu sem selo: {html[:900]}"
        atos.append(ato["id"])
    usados = _ler(casa_ri, """SELECT quantidade, quantidade_usada, usado_em, usado_por_ato_id
                               FROM cx_protocolo_atos WHERE id = ANY(%s) ORDER BY id""",
                  (linhas,))
    assert [(u["quantidade"], u["quantidade_usada"]) for u in usados] == [(1, 1)] * 3
    assert all(u["usado_em"] for u in usados)
    assert [u["usado_por_ato_id"] for u in usados] == atos
    with casa_ri["db"].connect() as con:
        sobra = [i for i in CXP.itens_disponiveis(con, cx["id"])
                 if i["codigo_ato"] == "16.22.2"]
    assert sobra == [], "sobrou saldo do 16.22.2"
