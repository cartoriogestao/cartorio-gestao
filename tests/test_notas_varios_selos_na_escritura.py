"""A escritura de mais de um imóvel: vários 13.1, cada um com o seu valor e o seu selo.

    «irei lavrar uma escritura com compra e venda de duas áreas (...) lançar
     2x o 13.1 com valores diferentes em uma escritura só» — a substituta,
     12/11/2026

O caixa já aceitava o mesmo item várias vezes, cada um com a sua base. Faltava o
SELO: a escritura aceitava um selo e um valor declarado. Agora o selo do ato
(`nt_atos.selo`) fica como sempre, e cada imóvel a mais ganha o SEU selo, o SEU
valor declarado e o SEU item pago do protocolo (`nt_ato_selos_extras`).

O selador é o de mentira da bancada (`selador_falso`, servidor local): nenhum
selo real é pedido ao TJMA.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
CARLA = "CARLA EXEMPLO LIMA"
# As duas áreas da compra e venda. A 2ª fica ABAIXO de R$ 100 mil de propósito:
# em centavos ela é 3.881.553, e o valor que `centavos()` lê como REAIS.
AREA_A = "205.863,95"      # 20586395 centavos -> 13.1.15
AREA_B = "38.815,53"       # 3881553 centavos  -> 13.1.8


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("carla", CARLA, SENHA, "USER")
    db.set_settings({"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"})
    c = cg_casa["app"].test_client()
    c.post("/login", data={"username": "carla", "password": SENHA,
                           "csrf_token": _token(
                               c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    con = sqlite3.connect(cg_casa["banco"])
    with con:
        con.execute("UPDATE cx_vigencias SET vigente=0")
        con.execute("INSERT INTO cx_vigencias (codigo, descricao, vigente) "
                    "VALUES (10022, '2026', 1)")
        for de, ate, codigo in (("30000,00", "60000,00", "13.1.8"),
                                ("150000,00", "250000,00", "13.1.15")):
            con.execute("INSERT INTO cx_faixas (tabela, vigencia, de, ate, "
                        "codigo_tj) VALUES (3, 10022, ?, ?, ?)",
                        (de, ate, codigo))
    con.close()
    return {**cg_casa, "cliente": c}


def _ato(casa, tipo="ESCRITURA", **campos) -> int:
    base = {"situacao": "LAVRADO", "livro": "30", "folha": "12",
            "termo": "1234", "valor_transacao": 24470190}   # as duas áreas somadas
    base.update(campos)
    if "termo" not in campos:
        base["termo"] = None            # o termo ? ?nico por s?rie: um por ato
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO nt_atos (tipo, serie, data, hora, situacao,
                   natureza, interessado, teor, teor_formato, lavrado_nome,
                   origem, criado_em)
               VALUES (?, 'LIVRO', '2026-11-12', '10:22', 'EM_LAVRATURA',
                       'Compra e venda', 'MARIA DA SILVA',
                       '<p>Teor da escritura.</p>', 'html', ?, 'MANUAL',
                       '2026-11-12T10:22:35')""", (tipo, CARLA))
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO nt_ato_partes (ato_id, nome, nome_norm, documento,
                                          ordem, testemunha, criado_em)
               VALUES (?,'MARIA DA SILVA','MARIA DA SILVA','00000004855',1,0,
                       '2026-11-12T10:22:35')""", (aid,))
        if base["termo"] is None and campos.get("termo", 1) is not None:
            base["termo"] = str(1000 + aid)
        sets = ", ".join(f"{k}=?" for k in base)
        con.execute(f"UPDATE nt_atos SET {sets} WHERE id=?",
                    (*base.values(), aid))
    con.close()
    return aid


def _postar(casa, ato_id, **dados) -> str:
    html = casa["cliente"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    return casa["cliente"].post(
        f"/notas/atos/{ato_id}", data={"csrf_token": _token(html), **dados},
        follow_redirects=True).get_data(as_text=True)


def _sql(casa, sql, params=()):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def _ato_linha(casa, ato_id):
    return _sql(casa, "SELECT * FROM nt_atos WHERE id=?", (ato_id,))[0]


def _razao(casa, ato_id):
    return _sql(casa, "SELECT numero FROM sd_selos WHERE tabela='nt_atos' "
                      "AND ato_id=? ORDER BY id", (ato_id,))


def _itens(casa, protocolo_id):
    return {r["codigo_ato"]: r for r in _sql(
        casa, "SELECT * FROM cx_protocolo_atos WHERE protocolo_id=?",
        (protocolo_id,))}


def _protocolo_pago(casa, codigos, quantidade=1):
    """O balcão: protocolo NOTAS com um item pago por código, em atendimento."""
    from protocolo_de_teste import atender_protocolo_pago
    with casa["db"].transaction() as con:
        return atender_protocolo_pago(con, usuario=CARLA, codigos=codigos,
                                      quantidade=quantidade, atribuicao="NOTAS")


def _pedidos(aparelho):
    return [json.loads(p["corpo"]) for p in aparelho.pedidos
            if p["caminho"].endswith("/selo/notas/ato-declarado/com-valor")]


def _codigo_no_aparelho(codigo_da_faixa: str) -> str:
    """O código que o aparelho recebe para esta faixa do caixa.

    A faixa (13.1.N) é o que o caixa cobra e o que fica anotado no ato. O
    hotfix das 18:35 (`dados_para_o_aparelho`) troca só o envelope do
    aparelho para o item pai 13.1, que é o código que o TJ conhece. Neste
    ramo a troca ainda pode não estar: o teste acompanha a função, e com os
    dois hotfixes juntos o aparelho tem de receber 13.1.
    """
    import ato_selado as AS
    trocar = getattr(AS, "dados_para_o_aparelho", None)
    if trocar is None:
        return codigo_da_faixa
    return trocar({"ato": {"codigo": codigo_da_faixa}})["ato"]["codigo"]


# ------------------------------------------------- o caso da compra e venda


def test_duas_areas_dois_13_1_cada_um_com_o_seu_selo_valor_e_item(casa):
    """O 1º selo com o valor da área A; o 2º, da área B, com o item da B."""
    from selador_de_bancada import ligar_o_selador
    aid = _ato(casa)
    p = _protocolo_pago(casa, ["13.1.15", "13.1.8"])
    with ligar_o_selador(casa, protocolo_pago=False) as aparelho:
        _postar(casa, aid, acao="selar", valor_do_selo=AREA_A)
        primeiro = _ato_linha(casa, aid)["selo"]
        assert (primeiro or "").strip(), "o 1º selo não saiu"
        html = _postar(casa, aid, acao="selar_extra", valor_do_selo=AREA_B,
                       protocolo_selo=str(p["protocolo_id"]))
    r = _ato_linha(casa, aid)
    # o selo do ato NÃO foi trocado pelo adicional
    assert r["selo"] == primeiro
    assert r["situacao"] == "LAVRADO"
    razao = _razao(casa, aid)
    assert len(razao) == 2 and razao[0]["numero"] == primeiro
    assert razao[1]["numero"] != primeiro
    # cada selo foi pedido com o SEU valor; o código no aparelho é o 13.1
    # quando a troca das 18:35 está no módulo, e a faixa segue no caixa
    um, dois = _pedidos(aparelho)
    assert um["ato"]["codigo"] == _codigo_no_aparelho("13.1.15")
    assert um["valorDeclarado"]["valorDeclarado"] == 205863.95
    assert dois["ato"]["codigo"] == _codigo_no_aparelho("13.1.8")
    assert dois["valorDeclarado"]["valorDeclarado"] == 38815.53
    # e gastou o item pago de CADA um: um do 13.1.15, um do 13.1.8
    itens = _itens(casa, p["protocolo_id"])
    assert itens["13.1.15"]["quantidade_usada"] == 1
    assert itens["13.1.8"]["quantidade_usada"] == 1
    # o que ficou anotado: o 1º (valor diferente do ato) e o adicional
    extras = _sql(casa, "SELECT * FROM nt_ato_selos_extras WHERE ato_id=? "
                        "ORDER BY ordem", (aid,))
    assert [(e["ordem"], e["codigo_tj"], e["valor_centavos"]) for e in extras] == [
        (1, "13.1.15", 20586395), (2, "13.1.8", 3881553)]
    assert extras[1]["selo"] == razao[1]["numero"]
    # teor e certidão leem o razão (os dois selos), e o arquivamento segue um só
    import ato_selado as AS
    con = sqlite3.connect(casa["banco"])
    try:
        etiquetas = AS.etiquetas_do_ato(con, "nt_atos", aid, r["selo"])
    finally:
        con.close()
    assert {e["numero"] for e in etiquetas} == {
        razao[0]["numero"], razao[1]["numero"]}
    assert not str(r["selo_arquivamento"] or "").strip()
    # a tela lista os dois selos, com item e valor
    assert "Selos desta escritura" in html
    assert razao[1]["numero"] in html and "13.1.8" in html and AREA_B in html


def test_o_mesmo_item_e_valor_nao_gasta_outro_selo_e_o_ato_fica_como_estava(casa):
    """A trava contra o selo em dobro vale para o MESMO item e valor."""
    from selador_de_bancada import ligar_o_selador
    aid = _ato(casa)
    p = _protocolo_pago(casa, ["13.1.15", "13.1.8"])
    with ligar_o_selador(casa, protocolo_pago=False):
        _postar(casa, aid, acao="selar", valor_do_selo=AREA_A)
        _postar(casa, aid, acao="selar_extra", valor_do_selo=AREA_B,
                protocolo_selo=str(p["protocolo_id"]))
        antes = _ato_linha(casa, aid)
        html = _postar(casa, aid, acao="selar_extra", valor_do_selo=AREA_B,
                       protocolo_selo=str(p["protocolo_id"]))
    assert "já tem o selo" in html and "outro imóvel" in html
    assert len(_razao(casa, aid)) == 2, "o mesmo imóvel pediu um 3º selo"
    assert _ato_linha(casa, aid)["selo"] == antes["selo"]


def test_extra_sem_item_pago_proprio_nao_sai_e_nao_mexe_no_ato(casa):
    """Mesmo valor confirmado, sem OUTRO 13.1 pago e livre: nada sai."""
    from selador_de_bancada import ligar_o_selador
    aid = _ato(casa)
    p = _protocolo_pago(casa, ["13.1.15"])          # só um 13.1.15 pago
    with ligar_o_selador(casa, protocolo_pago=False):
        _postar(casa, aid, acao="selar", valor_do_selo=AREA_A)
        antes = _ato_linha(casa, aid)
        html = _postar(casa, aid, acao="selar_extra", valor_do_selo=AREA_A,
                       confirmo_mesmo_valor="1",
                       protocolo_selo=str(p["protocolo_id"]))
    assert "SEU item 13.1.15" in html
    assert len(_razao(casa, aid)) == 1
    depois = _ato_linha(casa, aid)
    assert depois["selo"] == antes["selo"]
    assert depois["situacao"] == "LAVRADO", "a falha do adicional mexeu no ato"
    # e o ato não entrou na fila «aguardando cobertura»
    assert not _sql(casa, "SELECT 1 FROM cx_selo_aguardando WHERE tabela='nt_atos' "
                          "AND ato_id=?", (aid,))
    # nada foi gasto além do 1º selo
    assert _itens(casa, p["protocolo_id"])["13.1.15"]["quantidade_usada"] == 1


def test_item_ligado_ao_ato_nao_paga_o_selo_adicional(casa):
    """O item que a tela ligou ao ato paga o 1º selo; o 2º não pode usá-lo de novo."""
    import caixa_protocolo as CXP
    from selador_de_bancada import ligar_o_selador
    aid = _ato(casa)
    p = _protocolo_pago(casa, ["13.1.15"], quantidade=2)   # saldo 2
    item = _itens(casa, p["protocolo_id"])["13.1.15"]["id"]
    with casa["db"].transaction() as con:
        # a tela do ato ligou o ato ao item (gasta 1; sobra 1 no saldo)
        CXP.consumir_item(con, item, ato_id=aid, tabela="nt_atos",
                          agora="2026-11-12T10:00:00")
    with ligar_o_selador(casa, protocolo_pago=False):
        _postar(casa, aid, acao="selar", valor_do_selo=AREA_A)
        assert len(_razao(casa, aid)) == 1
        html = _postar(casa, aid, acao="selar_extra", valor_do_selo=AREA_A,
                       confirmo_mesmo_valor="1",
                       protocolo_selo=str(p["protocolo_id"]))
    assert len(_razao(casa, aid)) == 1, "o 2º selo saiu com o pagamento do 1º"
    assert "SEU item 13.1.15" in html
    assert _itens(casa, p["protocolo_id"])["13.1.15"]["quantidade_usada"] == 1


def test_dois_imoveis_de_mesmo_valor_com_dois_itens_pagos_saem_se_confirmado(casa):
    """Dois imóveis de valor igual existem: quem declara marca que são dois."""
    from selador_de_bancada import ligar_o_selador
    aid = _ato(casa)
    p = _protocolo_pago(casa, ["13.1.8"], quantidade=2)
    with ligar_o_selador(casa, protocolo_pago=False):
        _postar(casa, aid, acao="selar", valor_do_selo=AREA_B)
        sem = _postar(casa, aid, acao="selar_extra", valor_do_selo=AREA_B,
                      protocolo_selo=str(p["protocolo_id"]))
        assert "marque «É outro imóvel" in sem and len(_razao(casa, aid)) == 1
        _postar(casa, aid, acao="selar_extra", valor_do_selo=AREA_B,
                confirmo_mesmo_valor="1",
                protocolo_selo=str(p["protocolo_id"]))
    assert len(_razao(casa, aid)) == 2
    assert _itens(casa, p["protocolo_id"])["13.1.8"]["quantidade_usada"] == 2


# ------------------------------------------------- o que não pode


def test_selo_adicional_so_depois_do_selo_do_ato_e_so_na_escritura(casa):
    from selador_de_bancada import ligar_o_selador
    sem_selo = _ato(casa)
    procuracao = _ato(casa, tipo="PROCURACAO", selo="PROCUR000000AAAAAAAAAAAAAA01")
    com_selo_em_lavratura = _ato(casa, situacao="EM_LAVRATURA",
                                 selo="ESCRIT000000AAAAAAAAAAAAAA02")
    selado = _ato(casa, selo="ESCRIT000000AAAAAAAAAAAAAA04")
    with ligar_o_selador(casa, protocolo_pago=False) as aparelho:
        a = _postar(casa, sem_selo, acao="selar_extra", valor_do_selo=AREA_B)
        b = _postar(casa, procuracao, acao="selar_extra", valor_do_selo=AREA_B)
        c = _postar(casa, com_selo_em_lavratura, acao="selar_extra",
                    valor_do_selo=AREA_B)
        d = _postar(casa, selado, acao="selar_extra", valor_do_selo="")
    assert "Peça primeiro o selo do ato" in a
    assert "só existe na escritura" in b
    assert "lavrado e já selado" in c
    assert "Informe o valor declarado" in d
    assert not _pedidos(aparelho), "algum pedido de selo foi ao aparelho"


def test_a_tela_so_oferece_o_selo_adicional_na_escritura_ja_selada(casa):
    sem_selo = _ato(casa)
    com_selo = _ato(casa, selo="ESCRIT000000AAAAAAAAAAAAAA03")
    html0 = casa["cliente"].get(f"/notas/atos/{sem_selo}").get_data(as_text=True)
    html1 = casa["cliente"].get(f"/notas/atos/{com_selo}").get_data(as_text=True)
    assert 'value="selar_extra"' not in html0
    assert 'value="selar_extra"' in html1
    assert "Acrescentar outro selo deste ato" in html1
    assert 'value="selar"' not in html1          # o selo do ato segue sem botão
    # o campo do valor do selo está no formulário do 1º selo
    assert 'name="valor_do_selo"' in html0


def test_o_valor_abaixo_de_100_mil_cai_na_faixa_certa(casa):
    """3.881.553 centavos eram lidos como R$ 3,8 milhões e caíam na faixa de cima."""
    aid = _ato(casa, valor_transacao=3881553)
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert '<option value="13.1.8"' in html


def test_sem_valor_do_selo_o_primeiro_selo_sai_como_sempre(casa):
    """O campo em branco não muda nada: valor e item vêm do ato."""
    from selador_de_bancada import ligar_o_selador
    aid = _ato(casa, valor_transacao=3881553)
    _protocolo_pago(casa, ["13.1.8"])
    with ligar_o_selador(casa, protocolo_pago=False) as aparelho:
        _postar(casa, aid, acao="selar", codigo_tj="13.1.8", valor_do_selo="")
    assert (_ato_linha(casa, aid)["selo"] or "").strip()
    (pedido,) = _pedidos(aparelho)
    assert pedido["ato"]["codigo"] == _codigo_no_aparelho("13.1.8")
    assert pedido["valorDeclarado"]["valorDeclarado"] == 38815.53
    assert not _sql(casa, "SELECT 1 FROM nt_ato_selos_extras WHERE ato_id=?",
                    (aid,)), "sem valor do selo não se grava linha nenhuma"


def test_o_selo_do_ato_nao_pode_ser_trocado_por_o_valor_do_selo_errado(casa):
    """O item sai da faixa do valor digitado; valor fora das faixas não sela."""
    from selador_de_bancada import ligar_o_selador
    aid = _ato(casa)
    _protocolo_pago(casa, ["13.1.15"])
    with ligar_o_selador(casa, protocolo_pago=False) as aparelho:
        html = _postar(casa, aid, acao="selar", valor_do_selo="1.000.000,00")
    assert not (_ato_linha(casa, aid)["selo"] or "").strip()
    assert not _pedidos(aparelho)
    assert "faixa" in html


def test_lancar_no_livro_com_o_valor_do_selo_pede_o_item_do_valor(casa):
    """O «Lançar no livro» também aceita o valor deste selo (1º imóvel)."""
    from selador_de_bancada import ligar_o_selador
    from notas_pronto_para_a_censec import preparar
    aid = _ato(casa, situacao="EM_LAVRATURA", livro=None, folha=None,
               termo=None)
    _protocolo_pago(casa, ["13.1.15", "13.1.8"])
    preparar(casa["banco"], aid)
    with ligar_o_selador(casa, protocolo_pago=False) as aparelho:
        _postar(casa, aid, acao="lancar", paginas="2", codigo_tj="",
                valor_do_selo=AREA_A)
    r = _ato_linha(casa, aid)
    assert (r["livro"] or "").strip() and (r["selo"] or "").strip()
    (pedido,) = _pedidos(aparelho)
    assert pedido["ato"]["codigo"] == _codigo_no_aparelho("13.1.15")
    assert pedido["valorDeclarado"]["valorDeclarado"] == 205863.95
    (linha,) = _sql(casa, "SELECT * FROM nt_ato_selos_extras WHERE ato_id=?", (aid,))
    assert (linha["ordem"], linha["codigo_tj"]) == (1, "13.1.15")


def test_uma_linha_por_ato_e_ordem(casa):
    """Clicar duas vezes não grava dois selos: (ato, ordem) é único."""
    aid = _ato(casa)
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("INSERT INTO nt_ato_selos_extras (ato_id, ordem, codigo_tj, "
                    "valor_centavos, selo, criado_em) VALUES (?,2,'13.1.8',1,'A','x')",
                    (aid,))
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("INSERT INTO nt_ato_selos_extras (ato_id, ordem, "
                        "codigo_tj, valor_centavos, selo, criado_em) "
                        "VALUES (?,2,'13.1.8',1,'B','x')", (aid,))
    con.close()