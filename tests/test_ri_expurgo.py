"""
Testes do expurgo de ato de Registro de Imoveis lavrado em teste.

O QUE ELES CONFEREM
    As TRAVAS, uma por uma — porque a funcao apaga assento, e funcao que apaga
    assento se julga pelo que ela RECUSA, nao pelo que ela faz:

      - ato do acervo nao se expurga;
      - ato do meio da cadeia nao se expurga (quebraria o hash dos seguintes);
      - ato cancelado, e ato que cancelou outro, nao se expurgam;
      - ato citado por certidao viva nao se expurga;
      - ato em CTP fechada ou DOI entregue nao se expurga;
      - motivo curto e recusado;
      - e, quando pode, o ato sai, a ata fica, e a cadeia dos que ficaram
        continua conferindo.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ri_expurgo as EX                                    # noqa: E402
from ri_schema import hash_ato, init_ri_schema, verifica_cadeia  # noqa: E402

AGORA = "2026-08-19T09:00:00"
EXTENSO = "dezenove dias do mês de agosto do ano de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO", "ri_cns": "000000",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
MOTIVO = ("Ato lavrado em teste de implantação do sistema; selo cancelado no TJMA.")


@pytest.fixture()
def con():
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    init_ri_schema(c)
    yield c
    c.close()


def matricula(con, numero="4011", livro="2", origem="MANUAL"):
    cur = con.execute(
        """INSERT INTO ri_matriculas
           (numero, complemento, livro, livro_norm, tipo_ficha, situacao, conferido,
            origem, criado_em, teor_formato)
           VALUES (?,'',?,?,'ESTRUTURADA','ATIVA',1,?,?,'texto')""",
        (numero, livro, livro, origem, AGORA))
    return int(cur.lastrowid)


def ato(con, matricula_id, tipo, numero, *, teor="TEOR", origem="MANUAL",
        matricula_numero="4011", selo="SELO123", cancelado=0):
    anterior = con.execute("""SELECT hash_ato FROM ri_atos WHERE matricula_id=?
                              ORDER BY id DESC LIMIT 1""", (matricula_id,)).fetchone()
    ha = anterior["hash_ato"] if anterior else None
    h = hash_ato(matricula_numero, tipo, numero, "2026-08-18", teor, ha)
    cur = con.execute(
        """INSERT INTO ri_atos
           (matricula_id, tipo, numero, data_ato, teor, teor_formato, cancelado,
            acervo, origem, hash_ato, hash_anterior, lavrado_em, selo_texto,
            natureza_titulo, emolumentos, lavrado_nome)
           VALUES (?,?,?,'2026-08-18',?, 'texto', ?, 0, ?, ?, ?, ?, ?, 'NATUREZA',
                   'Total R$ 134,43', 'BEATRIZ')""",
        (matricula_id, tipo, numero, teor, cancelado, origem, h, ha, AGORA, selo))
    return int(cur.lastrowid)


# ------------------------------------------------------------------ travas


def test_ato_do_acervo_nao_se_expurga(con):
    m = matricula(con)
    a = ato(con, m, "AV", 1, origem="EOFICIO")
    razoes = EX.impedimentos(con, a)
    assert any("acervo" in r for r in razoes)
    with pytest.raises(EX.ExpurgoError, match="acervo"):
        EX.expurgar(con, a, sv=SV, agora=AGORA, data_extenso=EXTENSO, motivo=MOTIVO)


def test_ato_do_meio_da_cadeia_nao_se_expurga(con):
    m = matricula(con)
    primeiro = ato(con, m, "R", 1)
    ato(con, m, "AV", 2)
    razoes = EX.impedimentos(con, primeiro)
    assert any("último ato" in r for r in razoes)
    assert any("AV-02" in r for r in razoes), "a mensagem tem de dizer QUAIS vêm depois"


def test_o_ultimo_ato_pode_ser_expurgado(con):
    m = matricula(con)
    ato(con, m, "R", 1)
    ultimo = ato(con, m, "AV", 2)
    assert EX.impedimentos(con, ultimo) == []


def test_ato_ja_cancelado_nao_se_expurga(con):
    m = matricula(con)
    a = ato(con, m, "AV", 1, cancelado=1)
    assert any("já está cancelado" in r for r in EX.impedimentos(con, a))


def test_averbacao_que_cancelou_outro_ato_nao_se_expurga(con):
    m = matricula(con)
    alvo = ato(con, m, "R", 1)
    canceladora = ato(con, m, "AV", 2)
    con.execute("UPDATE ri_atos SET cancelado=1, cancelado_por_ato_id=? WHERE id=?",
                (canceladora, alvo))
    assert any("cancelou o R-01" in r for r in EX.impedimentos(con, canceladora))


def test_ato_citado_em_certidao_viva_nao_se_expurga(con):
    m = matricula(con)
    a = ato(con, m, "AV", 28)
    con.execute(
        """INSERT INTO ri_certidoes
           (numero, ano, tipo, matricula_id, matricula_numero, data_emissao,
            corpo, corpo_formato, cancelada, origem, emitida_em)
           VALUES (6, 2026, 'INTEIRO_TEOR', ?, '4011', '2026-08-18',
                   'certifico ... AV-28/4011 ... dou fé', 'html', 0, 'MANUAL', ?)""",
        (m, AGORA))
    assert any("certidão 6/2026" in r for r in EX.impedimentos(con, a))


def test_certidao_cancelada_nao_impede(con):
    m = matricula(con)
    a = ato(con, m, "AV", 28)
    con.execute(
        """INSERT INTO ri_certidoes
           (numero, ano, tipo, matricula_id, matricula_numero, data_emissao,
            corpo, corpo_formato, cancelada, origem, emitida_em)
           VALUES (6, 2026, 'INTEIRO_TEOR', ?, '4011', '2026-08-18',
                   'certifico ... AV-28/4011 ...', 'html', 1, 'MANUAL', ?)""",
        (m, AGORA))
    assert EX.impedimentos(con, a) == []


def test_ctp_fechada_impede(con):
    m = matricula(con)
    a = ato(con, m, "R", 1)
    con.execute("""INSERT INTO ri_ctp_remessas (competencia, situacao, gerado_em)
                   VALUES ('2026-08','FECHADA', ?)""", (AGORA,))
    con.execute("""INSERT INTO ri_ctp_itens (competencia, ato_id, matricula_id)
                   VALUES ('2026-08', ?, ?)""", (a, m))
    assert any("CTP da competência 2026-08" in r for r in EX.impedimentos(con, a))


def test_doi_entregue_impede(con):
    m = matricula(con)
    a = ato(con, m, "R", 1)
    con.execute("""INSERT INTO ri_doi_remessas (competencia, situacao, gerado_em)
                   VALUES ('2026-08','ENTREGUE', ?)""", (AGORA,))
    con.execute("""INSERT INTO ri_ctp_itens (competencia, ato_id, matricula_id)
                   VALUES ('2026-08', ?, ?)""", (a, m))
    assert any("DOI da competência 2026-08" in r for r in EX.impedimentos(con, a))


def test_motivo_curto_e_recusado(con):
    m = matricula(con)
    a = ato(con, m, "AV", 3)
    with pytest.raises(EX.ExpurgoError, match="quinze letras"):
        EX.expurgar(con, a, sv=SV, agora=AGORA, data_extenso=EXTENSO, motivo="erro")


# ------------------------------------------------------------------ o expurgo


def test_o_ato_sai_a_ata_fica_e_a_cadeia_continua_conferindo(con):
    m = matricula(con)
    ato(con, m, "R", 1, teor="R-01/4014 TITULO DE DOMINIO")
    ato(con, m, "AV", 2, teor="AV-02/4014 CONDICOES RESOLUTIVAS")
    terceiro = ato(con, m, "AV", 3, teor="AV-03/4014 FLORESTA PUBLICA TIPO B",
                   selo="AVESVD000000FGG3MHVL8PU1JW52")
    con.execute("""INSERT INTO ri_partes (matricula_id, ato_id, nome, papel)
                   VALUES (?,?,'MARIA REGO SILVA PEREIRA','adquirente')""",
                (m, terceiro))

    saida = EX.expurgar(con, terceiro, sv=SV, agora=AGORA, data_extenso=EXTENSO,
                        motivo=MOTIVO, selo_cancelado="AVESVD000000FGG3MHVL8PU1JW52",
                        usuario="jean")

    assert con.execute("SELECT COUNT(*) c FROM ri_atos WHERE id=?",
                       (terceiro,)).fetchone()["c"] == 0
    assert con.execute("SELECT COUNT(*) c FROM ri_partes WHERE ato_id=?",
                       (terceiro,)).fetchone()["c"] == 0
    assert con.execute("SELECT COUNT(*) c FROM ri_atos WHERE matricula_id=?",
                       (m,)).fetchone()["c"] == 2, "os outros dois atos ficam"

    guardado = con.execute("SELECT * FROM ri_expurgos WHERE id=?",
                           (saida["expurgo_id"],)).fetchone()
    assert guardado["ato_rotulo"] == "AV-03/4011"
    assert "FLORESTA PUBLICA TIPO B" in guardado["ato_teor"], "o teor tem de ficar na ata"
    assert guardado["selo_cancelado"] == "AVESVD000000FGG3MHVL8PU1JW52"
    assert "MARIA REGO" in guardado["partes_json"]

    restantes = [dict(r) | {"matricula_numero": "4011"} for r in con.execute(
        """SELECT id, tipo, numero, data_ato, teor, hash_ato FROM ri_atos
           WHERE matricula_id=? ORDER BY id""", (m,))]
    assert verifica_cadeia(restantes) == [], "a cadeia dos que ficaram tem de conferir"


def test_a_ata_diz_o_que_um_corregedor_precisa_saber(con):
    m = matricula(con)
    a = ato(con, m, "AV", 3, teor="AV-03/4014 FLORESTA PUBLICA TIPO B",
            selo="AVESVD000000FGG3MHVL8PU1JW52")
    saida = EX.expurgar(con, a, sv=SV, agora=AGORA, data_extenso=EXTENSO, motivo=MOTIVO,
                        selo_cancelado="AVESVD000000FGG3MHVL8PU1JW52", usuario="jean")
    ata = saida["ata"]
    for esperado in ("ATA DE OCORRÊNCIA", "AV-03/4011", "4011", "BEATRIZ",
                     "AVESVD000000FGG3MHVL8PU1JW52", MOTIVO,
                     "FLORESTA PUBLICA TIPO B", "jean", "CNS 000000", EXTENSO):
        assert esperado in ata, f"a ata tem de dizer {esperado!r}"


def test_o_numero_do_ato_volta_a_estar_livre(con):
    m = matricula(con)
    ato(con, m, "R", 1)
    a = ato(con, m, "AV", 2)
    EX.expurgar(con, a, sv=SV, agora=AGORA, data_extenso=EXTENSO, motivo=MOTIVO)
    proximo = con.execute("SELECT COALESCE(MAX(numero),0)+1 n FROM ri_atos WHERE matricula_id=?",
                          (m,)).fetchone()["n"]
    assert proximo == 2, "expurgado o AV-02, o proximo ato volta a ser o 2"


def test_expurgar_duas_vezes_o_mesmo_ato_nao_passa(con):
    m = matricula(con)
    a = ato(con, m, "AV", 3)
    EX.expurgar(con, a, sv=SV, agora=AGORA, data_extenso=EXTENSO, motivo=MOTIVO)
    with pytest.raises(EX.ExpurgoError, match="não existe"):
        EX.expurgar(con, a, sv=SV, agora=AGORA, data_extenso=EXTENSO, motivo=MOTIVO)
