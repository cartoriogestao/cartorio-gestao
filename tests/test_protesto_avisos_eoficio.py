"""Os avisos e editais do E-Ofício trazidos para cá — 21/10/2026.

O QUE ESTES TESTES GUARDAM
  - cada situação do E-Ofício vira a situação certa daqui, medida nos 1.678;
  - aviso «na rua» de título já resolvido não fica esperando entrega;
  - a segunda rodada não insere nada (a chave de origem);
  - o número é o do exercício, e não a chave interna do E-Ofício;
  - no PostgreSQL, a chave de origem é ÚNICA e PARCIAL: recusa a repetida e
    aceita quantos avisos e editais nascidos aqui (sem chave) houver.

Os dois testes do sandbox sobre as LISTAS (`apontados_sem_aviso`,
`apontados_antigos`, `esperando_entrega(hoje=)` e o aviso trazido fora do
upload) são do P-C, em `protesto_aviso.py` — lote LH06 —, e entram com ele.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto_aviso as AV  # noqa: E402
from bd_nativo import banco  # noqa: E402
import protesto_avisos_eoficio as PAE  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402

HOJE = "2026-10-21"


def _banco():
    con = conexao_de_teste()
    # `pt_atos.livro_id` aponta para `nu_livros`, e o PostgreSQL nativo
    # cobra a chave estrangeira já na criação: o núcleo vem antes.
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def _titulo(con, chave, situacao, protocolo, apontado_em):
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, situacao, origem,
               origem_chave, protocolo, criado_em)
           VALUES ('DMI', ?, ?, 'CRA', ?, ?, ?)""",
        (f"N{chave}", situacao, f"tbAvisoProtesto:{chave}.0", protocolo, HOJE))
    tid = cur.lastrowid
    con.execute("""INSERT INTO pt_devedores(titulo_id, nome) VALUES (?, 'MARIO EXEMPLO')""",
                (tid,))
    con.execute("""INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                       origem, criado_em) VALUES (?, 'APONTAMENTO', ?, '{}', 'EOFICIO', ?)""",
                (tid, apontado_em, HOJE))
    return tid


def _acervo():
    """O acervo do E-Ofício, com os tipos do arquivo de lá (chave REAL, bit
    INTEGER, data e texto TEXT)."""
    ac = conexao_de_teste()
    ac.executescript("""
      CREATE TABLE tbBoletoApto (intChave REAL, intChaveAP REAL, dtmApto TEXT,
        dtmBoleto TEXT, strCB_AP TEXT, strSacado TEXT, strSacadoDOC TEXT,
        strSacadoEND TEXT, strSacadoBairro TEXT, strSacadoCep TEXT,
        strSacadoCidade TEXT, strSacadoUF TEXT, strUSERID_I TEXT,
        intCodigoEntregador INTEGER, dtmEntregaConfirmada TEXT,
        bitEntregue INTEGER, bitPublicadoEdital INTEGER, bitAtivo INTEGER,
        strNossoNumeroBoleto TEXT);
      CREATE TABLE tbBoletoControleNEntrega (strCB_AP TEXT, dtmEntrega TEXT,
        intCodigoMotivoNaoEntrega INTEGER, bitEntregue INTEGER,
        strRecebidoPor TEXT, strObs TEXT);
      CREATE TABLE tbEntregador (intCodigo INTEGER, strNome TEXT);
      CREATE TABLE tbEdital (intchave REAL, strcb_ap TEXT, dtmpublicacao TEXT,
        strUSERID_Publicado TEXT, struserid TEXT, strCodigoCidadeIBGE TEXT);
      INSERT INTO tbEntregador VALUES (2, 'CARTORIO');
    """)
    return ac


def _aviso(ac, chave, chave_ap, protocolo, quando, *, ativo=1, edital=0,
           entregue=0, confirmada=None):
    ac.execute("""INSERT INTO tbBoletoApto VALUES (?,?,?,?,?, 'MARIO EXEMPLO',
                   '00000000191', 'RUA A, 1', 'CENTRO', '65900000',
                   'CIDADE EXEMPLO', 'MA', 'mario', 2, ?, ?, ?, ?, 'NN1')""",
               (chave, chave_ap, quando, quando, protocolo, confirmada, entregue,
                edital, ativo))


def test_cada_situacao_do_eoficio_vira_a_certa_aqui():
    con, ac = _banco(), _acervo()
    _titulo(con, 1, "APONTADO", "2610070001", "2026-10-07")     # na rua
    _titulo(con, 2, "PROTESTADO", "2609010001", "2026-09-01")   # foi a edital
    _titulo(con, 3, "PAGO", "2609020001", "2026-09-02")         # pago antes
    _titulo(con, 4, "INTIMADO", "2609030001", "2026-09-03")     # em mãos
    _aviso(ac, 101, 1, "2610070001", "2026-10-07")
    _aviso(ac, 102, 2, "2609010001", "2026-09-01", edital=1, entregue=1,
           confirmada="2026-09-05")
    _aviso(ac, 103, 3, "2609020001", "2026-09-02")
    _aviso(ac, 104, 4, "2609030001", "2026-09-03", entregue=1,
           confirmada="2026-09-04")
    _aviso(ac, 105, 1, "2610070001", "2026-10-01", ativo=0)     # substituído
    ac.execute("INSERT INTO tbBoletoControleNEntrega VALUES ('2609010001', "
               "'2026-09-05', 11, 0, NULL, NULL)")
    ac.execute("INSERT INTO tbBoletoControleNEntrega VALUES ('2609030001', "
               "'2026-09-04', NULL, 1, 'MARIO EXEMPLO', NULL)")
    ac.execute("INSERT INTO tbEdital VALUES (7, '2609010001', '2026-09-10', "
               "'mario', 'mario', '2199999')")
    r = PAE.carregar(con, ac, agora=f"{HOJE}T12:00:00")
    assert r["por_situacao"] == {"EMITIDO": 1, "EDITAL": 1, "CANCELADO": 2,
                                 "ENTREGUE": 1}
    assert r["editais_inseridos"] == 1
    sit = {row["origem_chave"]: row for row in banco(con).ler(
        "SELECT * FROM pt_avisos ORDER BY id")}
    assert sit["tbBoletoApto:101"]["situacao"] == "EMITIDO"
    assert sit["tbBoletoApto:102"]["motivo"] == 11              # Ausente
    assert sit["tbBoletoApto:102"]["edital_id"] is not None
    assert "resolvido (pago)" in sit["tbBoletoApto:103"]["observacao"]
    assert sit["tbBoletoApto:104"]["recebido_por"] == "MARIO EXEMPLO"
    assert sit["tbBoletoApto:104"]["entregador"] == "CARTORIO"
    assert sit["tbBoletoApto:105"]["situacao"] == "CANCELADO"
    assert {a["origem"] for a in sit.values()} == {"EOFICIO"}
    # o número é o do exercício, e não a chave interna do E-Ofício
    assert sorted(r_["numero"] for r_ in sit.values()) == [1, 2, 3, 4, 5]
    assert AV.proximo_numero(con, 2026) == 6
    edital = banco(con).um("SELECT * FROM pt_editais ORDER BY id")
    assert edital["origem"] == "EOFICIO"
    assert edital["origem_chave"] == "tbEdital:7"
    assert edital["aviso_id"] == sit["tbBoletoApto:102"]["id"]
    # a segunda rodada não insere nada
    r2 = PAE.carregar(con, ac, agora=f"{HOJE}T13:00:00")
    assert r2["avisos_inseridos"] == 0 and r2["editais_inseridos"] == 0
    assert r2["avisos_ja_estavam"] == 5
    assert r2["editais_ja_estavam"] == 1
    assert con.execute("SELECT count(*) FROM pt_avisos").fetchone()[0] == 5


def test_aviso_sem_titulo_aqui_e_contado_e_nao_entra():
    con, ac = _banco(), _acervo()
    _aviso(ac, 301, 99, "2610070009", "2026-10-07")             # título 99 não veio
    r = PAE.carregar(con, ac, agora=f"{HOJE}T12:00:00")
    assert r["avisos_sem_titulo"] == 1 and r["avisos_inseridos"] == 0
    assert con.execute("SELECT count(*) FROM pt_avisos").fetchone()[0] == 0


@pytest.mark.parametrize("tabela", ["pt_avisos", "pt_editais"])
def test_a_chave_de_origem_e_unica_e_parcial_no_postgresql(tabela):
    """O índice é o da produção: ÚNICO e com `WHERE origem_chave IS NOT NULL`."""
    con = _banco()
    indice = {"pt_avisos": "ux_pt_avisos_origem",
              "pt_editais": "ux_pt_editais_origem"}[tabela]
    linha = con.execute(
        "SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema() "
        "AND indexname = ?", (indice,)).fetchone()
    assert linha is not None, f"{indice} não existe no PostgreSQL"
    definicao = linha[0]
    assert definicao.startswith(f"CREATE UNIQUE INDEX {indice} ON ")
    assert definicao.endswith(
        f".{tabela} USING btree (origem_chave) WHERE (origem_chave IS NOT NULL)")


def test_o_indice_parcial_recusa_a_chave_repetida_e_aceita_varias_vazias():
    con = _banco()
    tid = _titulo(con, 1, "APONTADO", "2610070001", "2026-10-07")

    def aviso(numero, chave):
        return con.execute(
            """INSERT INTO pt_avisos(titulo_id, numero, ano, situacao,
                   emitido_em, criado_em, origem, origem_chave)
               VALUES (?, ?, 2026, 'EMITIDO', ?, ?, ?, ?)""",
            (tid, numero, HOJE, HOJE, "EOFICIO" if chave else None,
             chave)).lastrowid

    # três avisos nascidos aqui, sem chave: o índice não os vê
    for n in (1, 2, 3):
        aviso(n, None)
    primeiro = aviso(4, "tbBoletoApto:7")
    with pytest.raises(sqlite3.IntegrityError):
        aviso(5, "tbBoletoApto:7")
    assert con.execute(
        "SELECT count(*) FROM pt_avisos WHERE origem_chave IS NULL").fetchone()[0] == 3
    assert con.execute(
        "SELECT id FROM pt_avisos WHERE origem_chave = 'tbBoletoApto:7'").fetchone()[0] == primeiro
