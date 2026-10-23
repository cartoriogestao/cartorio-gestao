"""O AGENTE DO RTD/PJ — e os dois defeitos que ele achou na produção.

    «Agente RTDPJ: fiscaliza e resolver problemas do RTDPJ» — o oficial, 09/10/2026

O QUE ESTES TESTES GUARDAM
      - **o título que vira averbação tem saída** (`rg_titulo.concluir_pelo_ato`):
        o título n. 1 do RCPJ ficou «Qualificado» desde 11/09/2026 com as duas
        averbações já lavradas, porque `registrar` abre registro NOVO e
        `encerrar` só sabe «devolvido» e «cancelado»;
      - **o selo do ato não é o da prenotação** (`rg_registro.papel_dos_selos`):
        a etiqueta da averbação 378 saiu seis vezes com o selo 15.1;
      - **o agente acha os dois e conserta os dois**, com o antes e o depois na
        auditoria, e o que ele corrigiu volta no relatório para revisão;
      - **a Central fora do ar não vira fila vazia**;
      - **nenhum prazo é inventado**: o título parado sai com os dias contados.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
from banco_de_teste import conexao_de_teste  # noqa: E402

import gestor_rtdpj as GRT
import rg_registro as RG
import rg_schema as RGS
import rg_titulo as TIT
from nucleo_schema import init_nucleo_schema

AGORA = "2026-09-11T11:35:00"
EXTENSO = "onze de setembro de dois mil e vinte e seis"
HOJE = date(2026, 10, 9)
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO/MA",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA", "ri_cns": "000000",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro"}
PRENOT = "PRENOT000000O4L63SD87FHMG083"
AVERBA = "AVERBA000000MGUFASDY2S09MO57"


@pytest.fixture()
def con(tmp_path):
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    # `cx_protocolos` antes do RCPJ/RTD: `rg_titulos` aponta para ela (FK), e
    # o PostgreSQL cobra a FK na criacao.
    c.executescript("""
        CREATE TABLE cx_protocolos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT, interessado TEXT,
            data_abertura TEXT, situacao TEXT, valor_total TEXT,
            atribuicao TEXT);
        CREATE TABLE cx_protocolo_atos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, protocolo_id INTEGER,
            codigo_ato TEXT, valor_total TEXT, quitado INTEGER DEFAULT 0,
            lancamento_id INTEGER, usado_por_tabela TEXT,
            usado_por_ato_id INTEGER);
        CREATE TABLE sd_selos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT, texto TEXT,
            referencia TEXT, tabela TEXT, ato_id INTEGER, cancelado_em TEXT);
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user_id INTEGER,
            username_snapshot TEXT, action TEXT, entity_type TEXT,
            entity_id INTEGER, details TEXT, ip_address TEXT);
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT);
    """)
    RGS.init_rg_schema(c)
    return c


def o_caso_da_santa_isabel(con) -> dict:
    """O que a produção tinha em 09/10/2026, em miniatura: um registro antigo,
    um título para averbar nele, a averbação lavrada gastando o protocolo do
    título, e o selo da prenotação na coluna do ato."""
    con.execute("""INSERT INTO cx_protocolos (id, numero, interessado,
                       data_abertura, situacao, valor_total, atribuicao)
                   VALUES (1, '2026.09.17', 'Caixa Escolar Uex Santa Isabel',
                           '2026-09-11', 'A_PAGAR', '1.034,98', 'RCPJ')""")
    reg = RG.abrir_registro(con, serie="PJ_A", sv=SV, agora="2011-12-23T00:00:00",
                            data_extenso=EXTENSO, natureza="Ata de constituição",
                            requerente_nome="CAIXA ESCOLAR SANTA ISABEL")
    titulo = TIT.receber(con, atribuicao=TIT.RCPJ, sv=SV, agora=AGORA,
                         data_extenso=EXTENSO, data_apresentacao="2026-09-11",
                         apresentante="Caixa Escolar Uex Santa Isabel",
                         natureza="Ata e estatuto", protocolo_geral_id=1)
    TIT.qualificar(con, titulo["titulo_id"], resultado=TIT.POSITIVA, agora=AGORA)
    av = RG.lancar_averbacao(con, reg["registro_id"], sv=SV,
                             agora="2026-09-11T23:11:59", data_extenso=EXTENSO,
                             teor="Ata de Assembleia Geral Extraordinária.")
    for codigo, valor in (("15.1", "42,60"), ("15.9.1", "102,15")):
        con.execute("""INSERT INTO cx_protocolo_atos (protocolo_id, codigo_ato,
                           valor_total, usado_por_tabela, usado_por_ato_id)
                       VALUES (1, ?, ?, 'rg_atos', ?)""",
                    (codigo, valor, av["ato_id"]))
    for numero, codigo in ((PRENOT, "15.1"), (AVERBA, "15.9.1")):
        con.execute("""INSERT INTO sd_selos (numero, texto, referencia, tabela,
                           ato_id) VALUES (?, ?, ?, 'rg_atos', ?)""",
                    (numero, f"Selo: {numero}, Ato: {codigo}, Total R$ 1,00",
                     f"rg_atos:{av['ato_id']}:{codigo}:1", av["ato_id"]))
    con.execute("UPDATE rg_atos SET selo=?, etiqueta_impressoes=6 WHERE id=?",
                (PRENOT, av["ato_id"]))
    return {"registro_id": reg["registro_id"], "titulo_id": titulo["titulo_id"],
            "ato_id": av["ato_id"]}


def regras(achados) -> set[str]:
    return {a["regra"] for a in achados}


# --------------------------------------------------------- a régua do selo


def test_o_selo_do_ato_nao_e_o_da_prenotacao():
    """A averbação 378 tinha `[15.1, 15.9.1, 15.9.2]` e a coluna ficou com o
    primeiro. O do ato é o primeiro que não é prenotação nem arquivamento."""
    principal, arquivamento = RG.papel_dos_selos(
        [("15.1", PRENOT), ("15.9.1", AVERBA), ("15.9.2", "AVERBA2"),
         ("15.22", "ARQUIV1")])
    assert principal == AVERBA
    assert arquivamento == "ARQUIV1"


def test_so_a_prenotacao_ainda_e_melhor_que_coluna_vazia():
    assert RG.papel_dos_selos([("15.1", PRENOT), ("15.22", "ARQ")]) == (PRENOT, "ARQ")
    assert RG.papel_dos_selos([]) == (None, None)


# ------------------------------------------- a saída do título de averbação


def test_o_titulo_atendido_por_averbacao_se_conclui(con):
    caso = o_caso_da_santa_isabel(con)
    feito = TIT.concluir_pelo_ato(con, caso["titulo_id"], ato_id=caso["ato_id"],
                                  agora="2026-10-09T14:30:00", usuario="teste")
    t = TIT.um(con, caso["titulo_id"])
    assert t["situacao"] == TIT.REGISTRADO
    assert t["registro_id"] == caso["registro_id"]
    assert feito["pelo_protocolo"] is True
    assert "AV n." in t["observacao"]
    # Nada se lavrou: o livro tem os mesmos dois atos de antes.
    assert len(RG.atos_do(con, caso["registro_id"])) == 2


def test_o_registro_nao_conclui_titulo_por_este_caminho(con):
    """O ato de REGISTRO não serve: registro novo se lavra por `registrar`."""
    caso = o_caso_da_santa_isabel(con)
    registro = RG.atos_do(con, caso["registro_id"])[0]
    assert registro["tipo"] == "REGISTRO"
    with pytest.raises(TIT.TituloError):
        TIT.concluir_pelo_ato(con, caso["titulo_id"], ato_id=registro["id"],
                              agora="2026-10-09T14:30:00")


def test_titulo_sem_qualificacao_positiva_nao_se_conclui(con):
    caso = o_caso_da_santa_isabel(con)
    con.execute("UPDATE rg_titulos SET situacao='APRESENTADO' WHERE id=?",
                (caso["titulo_id"],))
    with pytest.raises(TIT.TituloError):
        TIT.concluir_pelo_ato(con, caso["titulo_id"], ato_id=caso["ato_id"],
                              agora="2026-10-09T14:30:00")


def test_a_etiqueta_da_averbacao_acha_o_titulo_pelo_protocolo(con):
    """A averbação não carrega `rg_registros.titulo_id` — o registro é do
    acervo —, e a etiqueta dela saía sem o número do protocolo."""
    caso = o_caso_da_santa_isabel(con)
    assert TIT.titulo_do_registro(con, caso["registro_id"]) is None
    assert TIT.titulo_do_ato(con, caso["ato_id"])["id"] == caso["titulo_id"]


# ------------------------------------------------------------ o agente


def test_o_agente_acha_os_dois_defeitos_da_producao(con):
    o_caso_da_santa_isabel(con)
    achados = GRT.conferir(con, HOJE, central=lambda: [])
    assert {GRT.TITULO_ATENDIDO, GRT.SELO_DA_ETIQUETA} <= regras(achados)
    # O título atendido não aparece também como «parado»: uma pendência, uma
    # linha.
    assert GRT.TITULO_PARADO not in regras(achados)
    assert not [a for a in achados if a["gravidade"] == "NAO_MEDIU"], achados


def test_o_agente_conserta_e_deixa_o_antes_e_o_depois(con):
    caso = o_caso_da_santa_isabel(con)
    feito = GRT.corrigir(con, HOJE, agora="2026-10-09T14:30:00",
                         escrever=lambda *_: None)
    assert feito["titulos"] == 1 and feito["selos"] == 1
    assert TIT.um(con, caso["titulo_id"])["situacao"] == TIT.REGISTRADO
    selo = con.execute("SELECT selo FROM rg_atos WHERE id=?",
                       (caso["ato_id"],)).fetchone()["selo"]
    assert selo == AVERBA
    trilha = {r["action"]: json.loads(r["details"]) for r in con.execute(
        "SELECT action, details FROM audit_logs WHERE username_snapshot='gestor'")}
    assert trilha["GESTOR_RTDPJ_SELO_PRINCIPAL"]["antes"]["selo"] == PRENOT
    assert trilha["GESTOR_RTDPJ_TITULO_CONCLUIDO"]["antes"]["situacao"] == "QUALIFICADO"
    # Depois do conserto, as duas pendências somem e o que se fez volta para
    # o oficial revisar — sem tarefa.
    achados = GRT.conferir(con, HOJE, central=lambda: [])
    assert GRT.TITULO_ATENDIDO not in regras(achados)
    assert GRT.SELO_DA_ETIQUETA not in regras(achados)
    corrigidos = [a for a in achados if a["regra"] == GRT.CORRIGIDO]
    assert len(corrigidos) == 2
    assert GRT.CORRIGIDO in GRT.REGRAS_SEM_TAREFA
    # E a segunda rodada não conserta de novo.
    assert GRT.corrigir(con, HOJE, escrever=lambda *_: None)["selos"] == 0


def test_a_central_fora_do_ar_nao_vira_fila_vazia(con):
    def caiu():
        raise OSError("sem internet")
    achados = GRT.regra_central(con, HOJE, caiu)
    assert [a["regra"] for a in achados] == [GRT.CENTRAL_NAO_LIDA]
    assert "NÃO quer dizer que não há" in achados[0]["detalhe"]


def test_pedido_na_central_vira_pendencia(con):
    fila = [{"Protocolo": "ABC123", "Servico": {"Nome": "Notificação"},
             "Cliente": {"Nome": "FULANO"}}]
    achados = GRT.regra_central(con, HOJE, lambda: fila)
    assert achados[0]["regra"] == GRT.CENTRAL_PENDENTE
    assert "ABC123" in achados[0]["titulo"]
    assert GRT.CENTRAL_PENDENTE not in GRT.REGRAS_SEM_TAREFA


def test_o_titulo_parado_conta_os_dias_e_nao_inventa_prazo(con):
    TIT.receber(con, atribuicao=TIT.RTD, sv=SV, agora=AGORA,
                data_extenso=EXTENSO, data_apresentacao="2026-10-01",
                apresentante="FULANO")
    achados = GRT.regra_titulo_parado(con, HOJE)
    assert len(achados) == 1
    assert "há 8 dia(s)" in achados[0]["titulo"]
    assert achados[0]["prazo"] is None
    assert "Não é prazo da lei" in achados[0]["detalhe"]


def test_o_titulo_de_hoje_nao_esta_parado(con):
    TIT.receber(con, atribuicao=TIT.RTD, sv=SV, agora=AGORA,
                data_extenso=EXTENSO, data_apresentacao=HOJE.isoformat())
    assert GRT.regra_titulo_parado(con, HOJE) == []


def test_o_protocolo_com_selo_gasto_e_sem_pagamento_e_achado_da_gestao(con):
    o_caso_da_santa_isabel(con)
    achados = GRT.regra_sem_pagamento(con, HOJE)
    assert len(achados) == 1
    assert achados[0]["setor"] == GRT.SETOR_GESTAO
    assert "R$ 144,75" in achados[0]["titulo"]
    assert GRT.SEM_PAGAMENTO in GRT.REGRAS_SEM_TAREFA


def test_o_numero_repetido_do_acervo_aparece_e_nao_vira_tarefa(con):
    for chave in ("tbRegistroTD:3.0", "tbRegistroTD:4.0"):
        r = RG.abrir_registro(con, serie="TD_B", sv=SV, agora="2020-04-24T00:00:00",
                              data_extenso=EXTENSO, origem="EOFICIO",
                              origem_chave=chave)
        con.execute("UPDATE rg_registros SET numero=1256 WHERE id=?",
                    (r["registro_id"],))
    achados = GRT.regra_registro_repetido(con, HOJE)
    assert len(achados) == 1 and "1256" in achados[0]["titulo"]
    assert GRT.REGISTRO_REPETIDO in GRT.REGRAS_SEM_TAREFA


def test_o_livro_de_protocolo_sem_o_termo_do_dia(con):
    TIT.receber(con, atribuicao=TIT.RCPJ, sv=SV, agora=AGORA,
                data_extenso=EXTENSO, data_apresentacao="2026-09-11")
    achados = GRT.regra_encerramento_diario(con, HOJE)
    assert [a["regra"] for a in achados] == [GRT.ENCERRAMENTO_DIARIO]
    assert "11/09/2026" in achados[0]["titulo"]


def test_o_livro_de_serie_gravada_em_minuscula_tambem_e_conferido(con, monkeypatch):
    """`escrituracao.abrir_livro` aceita a série em qualquer caixa e a grava
    como veio. O `LIKE 'PJ%'` do SQLite não ligava para caixa; o do PostgreSQL
    liga, e o livro sumiria da conferência calado (revisão do L032: `ILIKE`)."""
    import escrituracao as ESC
    livro = ESC.abrir_livro(con, "pj_a", sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert con.execute("SELECT serie FROM nu_livros WHERE id=?",
                       (livro,)).fetchone()["serie"] == "pj_a"
    monkeypatch.setattr(ESC, "conferir_livro", lambda con, livro_id: {
        "achados": ["a folha 3 está em branco"], "serie_nome": "Livro A do RCPJ"})
    achados = GRT.regra_livro(con, HOJE)
    assert [a["chave"] for a in achados] == [f"RTDPJ_LIVRO:{livro}:0"]


def test_o_que_o_agente_corrigiu_volta_qualquer_que_seja_a_caixa_da_acao(con):
    """O `LIKE 'GESTOR_RTDPJ_%'` do SQLite não ligava para caixa; a conversão
    manteve isso com `ILIKE` (revisão do L032)."""
    con.execute("""INSERT INTO audit_logs (ts, username_snapshot, action, details)
                   VALUES ('2026-10-08T10:00:00', 'gestor', ?, ?)""",
                ("gestor_rtdpj_selo_principal",
                 json.dumps({"resumo": "selo do ato no lugar do da prenotação"})))
    achados = GRT.regra_corrigido(con, HOJE)
    assert [a["titulo"] for a in achados] == ["selo do ato no lugar do da prenotação"]


def test_a_regra_que_quebra_vira_nao_mediu(con, monkeypatch):
    def quebra(con, hoje):
        raise RuntimeError("coluna nova")
    monkeypatch.setattr(GRT, "REGRAS", ((GRT.LIVRO, quebra),))
    achados = GRT.conferir(con, HOJE, central=lambda: [])
    assert achados[0]["gravidade"] == "NAO_MEDIU"


def test_todas_as_regras_tem_rotulo():
    for nome, _ in GRT.REGRAS:
        assert nome in GRT.ROTULOS, nome
    assert GRT.CENTRAL_NAO_LIDA in GRT.ROTULOS


def test_o_modulo_nao_lavra_nao_sela_e_nao_cobra():
    """A régua das fraudes, do CNIB e do usucapião: o agente conserta
    anotação, e não pratica ato."""
    proibidos = ("lavrar", "selar", "cobrar", "numerar", "abrir_registro",
                 "lancar_averbacao", "obter_selo")
    publicos = [n for n in dir(GRT) if not n.startswith("_")]
    for nome in publicos:
        assert not any(p in nome.lower() for p in proibidos), nome
