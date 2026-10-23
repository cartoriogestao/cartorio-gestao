"""Versao final do lavrar RI: emolumentos + espaco do selo + itens/protocolo.

Pedido do oficial (15/09/2026): a versao final a ser lavrada inclui no fim
emolumentos calculados e espaco para o selo; a tabela de itens acompanha o
protocolo; sem protocolo, escolhe-se com texto completo; a relacao pode
constar no carimbo do selo (regua do RCPJ / selo_no_papel).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from banco_de_teste import conexao_de_teste  # noqa: E402

import ri_lavrar_teor as RITEOR  # noqa: E402
import ri_odt  # noqa: E402


def test_versao_final_tem_emolumentos_e_espaco_do_selo():
    itens = [{
        "codigo_tj": "16.3",
        "descricao": "Registro de compra e venda",
        "emolumentos": "100,00",
        "ferc": "3,00",
        "fadep": "4,00",
        "femp": "4,00",
        "ferrfis": None,
        "total": "111,00",
    }]
    teor = RITEOR.versao_final_para_lavrar("AV-01 — texto do ato.", itens)
    assert "AV-01 — texto do ato." in teor
    assert RITEOR.MARCA_EMOLUMENTOS in teor
    assert "Emol R$ 100,00" in teor
    assert RITEOR.MARCA_SELO in teor
    assert "selo / verificacao" in teor
    assert "relacao de emolumentos pode constar no carimbo" in teor


def test_sem_fecho_antigo_nao_duplica():
    itens = [{"codigo_tj": "16.9", "descricao": "X", "emolumentos": "1,00",
              "total": "1,00", "ferc": None, "fadep": None, "femp": None,
              "ferrfis": None}]
    um = RITEOR.versao_final_para_lavrar("corpo", itens)
    dois = RITEOR.versao_final_para_lavrar(um, itens)
    assert dois.count(RITEOR.MARCA_EMOLUMENTOS) == 1
    assert dois.count(RITEOR.MARCA_SELO) == 1


def test_itens_do_protocolo_acompanham_quando_ha():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE cx_protocolos(
            id INTEGER PRIMARY KEY, numero TEXT, interessado TEXT,
            situacao TEXT, atribuicao TEXT);
        CREATE TABLE cx_protocolo_atos(
            id INTEGER PRIMARY KEY, protocolo_id INTEGER, codigo_ato TEXT,
            descricao TEXT, quantidade INTEGER, valor_total TEXT,
            servico_codigo INTEGER, usado_em TEXT);
        INSERT INTO cx_protocolos VALUES (1,'P-1','Fulano','ABERTO','RI');
        INSERT INTO cx_protocolo_atos VALUES
            (10,1,'16.3','Registro completo',1,'111,00',100,NULL),
            (11,1,'16.9','Averbacao usada',1,'50,00',101,'2026-01-01');
    """)
    abertos = RITEOR.protocolos_do_caixa_abertos(con)
    assert abertos and abertos[0]["numero"] == "P-1"
    itens = RITEOR.itens_do_protocolo_disponiveis(con, 1)
    assert len(itens) == 1
    assert itens[0]["codigo_ato"] == "16.3"
    assert "Registro completo" in itens[0]["descricao"]
    assert RITEOR.itens_do_protocolo_disponiveis(con, None) == []


def test_sem_protocolo_catalogo_com_texto_completo(monkeypatch):
    monkeypatch.setattr(
        "ato_selado.itens_medidos_do_ato_do_ri",
        lambda: [("16.3", 40), ("16.9", 10)],
    )
    con = conexao_de_teste()
    con.executescript("""
        CREATE TABLE cx_vigencias(codigo INTEGER, vigente INTEGER);
        INSERT INTO cx_vigencias VALUES (2026, 1);
        CREATE TABLE cx_servicos(
            codigo INTEGER, codigo_tj TEXT, descricao TEXT, ativo INTEGER);
        CREATE TABLE cx_servico_valores(
            servico INTEGER, vigencia INTEGER, emolumentos TEXT,
            ferc TEXT, femp TEXT, fadep TEXT, ferrfis TEXT, total TEXT);
        INSERT INTO cx_servicos VALUES
            (1,'16.3','REGISTRO DE COMPRA E VENDA — TEXTO COMPLETO',1),
            (2,'16.9','AVERBACAO GENERICA — TEXTO COMPLETO',1);
        INSERT INTO cx_servico_valores VALUES
            (1,2026,'100,00','3,00','4,00','4,00',NULL,'111,00'),
            (2,2026,'50,00','1,50','2,00','2,00',NULL,'55,50');
    """)
    cat = RITEOR.itens_com_texto_completo(con)
    assert [c["codigo_tj"] for c in cat] == ["16.3", "16.9"]
    assert "TEXTO COMPLETO" in cat[0]["descricao"]
    assert cat[0]["emolumentos"] == "100,00"


def test_carimbo_inclui_relacao_de_emolumentos():
    # Texto no padrao dos 25.634 selos da casa.
    texto = (
        "Poder Judiciario - TJMA. Selo: REGAVD000000003M1XKR7TEX6G33, "
        "15/09/2026 10:00:00, Ato: 16.3, Parte(s): FULANO, "
        "Total R$ 111,00 Emol R$ 100,00 FERC R$ 3,00 FADEP R$ 4,00 "
        "FEMP R$ 4,00 Consulte em https://selo.tjma.jus.br"
    )
    valores = RITEOR.valores_para_o_carimbo(texto)
    assert "Total R$" in valores
    assert "Emol R$" in valores
    html = ri_odt.bloco_selo_html(texto)
    assert "selo-valores" in html
    assert "Emolumentos:" in html
    assert "Total R$" in html


def test_resolver_une_prenotacao_e_caixa_por_fk():
    """Com ri_protocolo_id preenchido, a prenotacao traz o caixa sozinha."""
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE ri_protocolos(
            id INTEGER PRIMARY KEY, numero TEXT, situacao TEXT);
        CREATE TABLE cx_protocolos(
            id INTEGER PRIMARY KEY, numero TEXT, interessado TEXT,
            situacao TEXT, ri_protocolo_id INTEGER);
        CREATE TABLE cx_depositos(
            id INTEGER PRIMARY KEY, numero TEXT, data TEXT,
            depositante TEXT, valor TEXT, saldo TEXT,
            protocolo_id INTEGER, encerrado INTEGER, observacao TEXT,
            ri_protocolo_id INTEGER);
        CREATE TABLE cx_protocolo_atos(
            id INTEGER PRIMARY KEY, protocolo_id INTEGER, codigo_ato TEXT,
            descricao TEXT, quantidade INTEGER, valor_total TEXT,
            servico_codigo INTEGER, usado_em TEXT);
        INSERT INTO ri_protocolos VALUES (7, '11568', 'ABERTO');
        INSERT INTO cx_protocolos VALUES (90, 'CX-90', 'Fulano', 'ABERTO', 7);
        INSERT INTO cx_protocolo_atos VALUES
            (1, 90, '16.3', 'Registro', 1, '111,00', 1, NULL);
        INSERT INTO cx_depositos VALUES
            (1, 'DP2026.09.9', '2026-09-15', 'Fulano', '43,37', '43,37',
             NULL, 0, 'previo', 7);
    """)
    r = RITEOR.resolver_protocolo_caixa(con, ri_protocolo_id=7)
    assert r["origem"] == "ligado"
    assert r["protocolo_caixa_id"] == 90
    assert r["caixa"]["numero"] == "CX-90"
    assert len(r["depositos"]) == 1
    assert r["depositos"][0]["numero"] == "DP2026.09.9"
    itens = RITEOR.itens_do_protocolo_disponiveis(con, r["protocolo_caixa_id"])
    assert itens and itens[0]["codigo_ato"] == "16.3"


def test_resolver_escolha_manual_vence_a_fk():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE ri_protocolos(
            id INTEGER PRIMARY KEY, numero TEXT, situacao TEXT);
        CREATE TABLE cx_protocolos(
            id INTEGER PRIMARY KEY, numero TEXT, interessado TEXT,
            situacao TEXT, ri_protocolo_id INTEGER);
        CREATE TABLE cx_depositos(
            id INTEGER PRIMARY KEY, numero TEXT, data TEXT,
            depositante TEXT, valor TEXT, saldo TEXT,
            protocolo_id INTEGER, encerrado INTEGER, observacao TEXT,
            ri_protocolo_id INTEGER);
        INSERT INTO ri_protocolos VALUES (7, '11568', 'ABERTO');
        INSERT INTO cx_protocolos VALUES
            (90, 'CX-90', 'Fulano', 'ABERTO', 7),
            (91, 'CX-91', 'Outro', 'ABERTO', NULL);
    """)
    r = RITEOR.resolver_protocolo_caixa(
        con, protocolo_caixa_id=91, ri_protocolo_id=7)
    assert r["origem"] == "escolhido"
    assert r["protocolo_caixa_id"] == 91


def test_resolver_sem_fk_mostra_so_deposito_sem_inventar_join():
    """Sem ri_protocolo_id no caixa, nao adivinha — so expoe deposito."""
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE ri_protocolos(
            id INTEGER PRIMARY KEY, numero TEXT, situacao TEXT);
        CREATE TABLE cx_protocolos(
            id INTEGER PRIMARY KEY, numero TEXT, interessado TEXT,
            situacao TEXT, ri_protocolo_id INTEGER);
        CREATE TABLE cx_depositos(
            id INTEGER PRIMARY KEY, numero TEXT, data TEXT,
            depositante TEXT, valor TEXT, saldo TEXT,
            protocolo_id INTEGER, encerrado INTEGER, observacao TEXT,
            ri_protocolo_id INTEGER);
        INSERT INTO ri_protocolos VALUES (7, '11568', 'ABERTO');
        INSERT INTO cx_protocolos VALUES
            (90, 'CX-90', 'Fulano', 'ABERTO', NULL);
        INSERT INTO cx_depositos VALUES
            (1, 'DP2026.09.9', '2026-09-15', 'Fulano', '43,37', '43,37',
             NULL, 0, 'previo', 7);
    """)
    r = RITEOR.resolver_protocolo_caixa(con, ri_protocolo_id=7)
    assert r["origem"] == "nenhum"
    assert r["protocolo_caixa_id"] is None
    assert len(r["depositos"]) == 1


def test_versao_final_mantem_emolumentos_no_teor_lavrado():
    """Nao mover emolumentos para previa-only — oficial exige no teor final."""
    teor = RITEOR.versao_final_para_lavrar(
        "AV-01 texto.",
        [{"codigo_tj": "16.3", "descricao": "Reg", "emolumentos": "10,00",
          "total": "11,00", "ferc": "1,00", "fadep": None, "femp": None,
          "ferrfis": None}],
    )
    assert RITEOR.MARCA_EMOLUMENTOS in teor
    assert RITEOR.MARCA_SELO in teor
    assert "Emol R$ 10,00" in teor



def test_caixa_ligado_aceita_a_pagar(tmp_path):
    """OP A_PAGAR vinculada a prenotacao aparece no lavrar (caso 3110/Edilson)."""
    import sqlite3
    import ri_lavrar_teor as RIL
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE cx_protocolos(
            id INTEGER PRIMARY KEY, numero TEXT, interessado TEXT,
            situacao TEXT, ri_protocolo_id INTEGER, atribuicao TEXT);
        CREATE TABLE ri_protocolos(id INTEGER PRIMARY KEY, numero INTEGER);
        CREATE TABLE cx_depositos(
            id INTEGER PRIMARY KEY, numero TEXT, data TEXT, depositante TEXT,
            valor TEXT, saldo TEXT, protocolo_id INTEGER, ri_protocolo_id INTEGER,
            encerrado INTEGER, observacao TEXT);
    """)
    con.execute("INSERT INTO ri_protocolos(id, numero) VALUES (1583, 11571)")
    con.execute(
        "INSERT INTO cx_protocolos"
        " (id, numero, interessado, situacao, ri_protocolo_id, atribuicao)"
        " VALUES (21371, '2026.09.23', 'EDILSON', 'A_PAGAR', 1583, 'RI')")
    ligado = RIL.caixa_ligado_a_prenotacao(con, 1583)
    assert ligado is not None
    assert ligado["numero"] == "2026.09.23"
    lista = RIL.protocolos_do_caixa_abertos(con)
    assert any(x["numero"] == "2026.09.23" for x in lista)
    resolvido = RIL.resolver_protocolo_caixa(con, ri_protocolo_id=1583)
    assert resolvido["origem"] == "ligado"
    assert resolvido["protocolo_caixa_id"] == 21371


def test_o_recorte_por_atribuicao_separa_os_protocolos():
    """Relato #76, 17/09/2026: na certidao do RI o protocolo de firma e ruido.

    **Medido na producao em 17/09/2026, 15h30**: sem o recorte, os 80 da
    janela sao **33 do RI**, 32 do RCPN, 6 de firma, 5 do protesto, 3 das
    notas e 1 do RCPJ — 47 linhas que nao servem a uma certidao de imovel.

    O caso que separa: dois protocolos abertos, um do RI e um de firma. Com
    `atribuicao="RI"` fica um; sem ela, os dois — o recorte e opcional, e
    `None` nao pode esconder protocolo nenhum.
    """
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE cx_protocolos(
            id INTEGER PRIMARY KEY, numero TEXT, interessado TEXT,
            situacao TEXT, atribuicao TEXT);
        INSERT INTO cx_protocolos VALUES
            (1, '2026.09.23', 'EDILSON', 'A_PAGAR', 'RI'),
            (2, '2026.09.24', 'FULANA',  'ABERTO',  'FIRMAS'),
            (3, '2026.09.25', 'SICRANO', 'ABERTO',  'RI'),
            (4, '2026.09.10', 'ENTREGUE', 'ENTREGUE', 'RI');
    """)
    do_ri = RITEOR.protocolos_do_caixa_abertos(con, atribuicao="RI")
    assert [x["numero"] for x in do_ri] == ["2026.09.25", "2026.09.23"]
    todas = RITEOR.protocolos_do_caixa_abertos(con)
    assert {x["numero"] for x in todas} == {
        "2026.09.23", "2026.09.24", "2026.09.25"}
    # O recorte de atribuicao NAO muda o que ja valia: protocolo encerrado fica
    # fora das duas listas, e A_PAGAR entra nas duas.
    assert "2026.09.10" not in {x["numero"] for x in todas}
