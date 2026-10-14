"""
Testes da numeracao por serventia, da renumeracao de matricula e da correcao
de partes.

O CASO REAL QUE ORIGINOU CADA UM
    Em 18/08/2026 o sistema abriu a matricula 4011 no livro "2" quando a
    serventia ja tinha a 4013 no volume "2S", porque contava por volume em vez
    de por serventia. E o R-01 gravou o INCRA como "adquirente" e a adquirente
    sem papel, deixando a matricula SEM TITULAR ATIVO.

    Cada teste abaixo reproduz um desses fatos e exige o comportamento correto.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ri_correcoes as RC                                   # noqa: E402
from ri_schema import hash_ato, init_ri_schema, verifica_cadeia   # noqa: E402

AGORA = "2026-08-19T09:00:00"


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


def matricula(con, numero, livro, origem="MANUAL"):
    cur = con.execute(
        """INSERT INTO ri_matriculas
           (numero, complemento, livro, livro_norm, tipo_ficha, situacao, conferido,
            origem, criado_em, teor_formato)
           VALUES (?,'',?,?,'ESTRUTURADA','ATIVA',1,?,?,'texto')""",
        (str(numero), livro, livro, origem, AGORA))
    return int(cur.lastrowid)


def numeracao(con, livro, proximo, maior):
    con.execute("""INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso, fixado_em)
                   VALUES (?,?,?,?)""", (livro, proximo, maior, AGORA))


def ato(con, matricula_id, tipo, numero, matricula_numero, teor):
    anterior = con.execute("""SELECT hash_ato FROM ri_atos WHERE matricula_id=?
                              ORDER BY id DESC LIMIT 1""", (matricula_id,)).fetchone()
    ha = anterior["hash_ato"] if anterior else None
    h = hash_ato(matricula_numero, tipo, numero, "2026-08-18", teor, ha)
    cur = con.execute(
        """INSERT INTO ri_atos
           (matricula_id, tipo, numero, data_ato, teor, teor_formato, cancelado,
            acervo, origem, hash_ato, hash_anterior, lavrado_em)
           VALUES (?,?,?,'2026-08-18',?,'texto',0,0,'MANUAL',?,?,?)""",
        (matricula_id, tipo, numero, teor, h, ha, AGORA))
    return int(cur.lastrowid)


# ------------------------------------------------------------ serie do livro


@pytest.mark.parametrize("livro,serie", [
    ("2", "2"), ("2C", "2"), ("2-C", "2"), ("2S", "2"), ("2 S", "2"),
    ("3", "3"), ("1A", "1"), ("1", "1"),
])
def test_a_letra_e_o_volume_nao_a_serie(livro, serie):
    assert RC.serie_do_livro(livro) == serie


def test_livro_3_nao_se_mistura_com_o_livro_2(con):
    matricula(con, 4013, "2S")
    matricula(con, 1650, "3")
    assert RC.maior_numero_da_serie(con, "2") == 4013
    assert RC.maior_numero_da_serie(con, "3") == 1650, \
        "Registro Auxiliar tem numeracao propria"


# --------------------------------------------- o erro do dia 18, reproduzido


def test_o_proximo_numero_olha_a_serventia_e_nao_o_volume(con):
    """O caso real: livro '2' em 4010, mas a serventia ja usou a 4013 no '2S'."""
    matricula(con, 4010, "2")
    matricula(con, 4012, "2R")
    matricula(con, 4013, "2S")
    numeracao(con, "2", 4011, 4010)
    numeracao(con, "2R", 4013, 4012)
    numeracao(con, "2S", 4014, 4013)

    assert RC.proximo_numero(con, "2") == 4014, \
        "contar por volume daria 4011, que a serventia ja usou"


def test_numero_em_uso_encontra_a_matricula_em_qualquer_volume(con):
    matricula(con, 4013, "2S")
    achada = RC.numero_em_uso(con, "2", 4013)
    assert achada is not None and achada["livro"] == "2S"


def test_numeracao_atrasada_nao_faz_o_numero_andar_para_tras(con):
    numeracao(con, "2", 5000, 4999)
    assert RC.proximo_numero(con, "2") == 5000


# --------------------------------------------------------------- renumeracao


def test_renumerar_4011_para_4014_refaz_a_cadeia(con):
    m = matricula(con, 4011, "2")
    matricula(con, 4013, "2S")
    ato(con, m, "R", 1, "4011", "R-01/4014 TITULO DE DOMINIO")
    ato(con, m, "AV", 2, "4011", "AV-02/4014 CONDICOES RESOLUTIVAS")

    antes = [dict(r) | {"matricula_numero": "4014"} for r in con.execute(
        "SELECT id,tipo,numero,data_ato,teor,hash_ato FROM ri_atos ORDER BY id")]
    assert verifica_cadeia(antes), "com o numero novo, a cadeia antiga NAO confere"

    saida = RC.renumerar_matricula(con, m, 4014, agora=AGORA,
                                   motivo="Número já usado pela serventia no volume 2S")

    assert saida["de"] == "4011" and saida["para"] == "4014"
    assert len(saida["atos"]) == 2
    assert all(a["hash_antigo"] != a["hash_novo"] for a in saida["atos"])

    depois = [dict(r) | {"matricula_numero": "4014"} for r in con.execute(
        "SELECT id,tipo,numero,data_ato,teor,hash_ato FROM ri_atos ORDER BY id")]
    assert verifica_cadeia(depois) == [], "depois de renumerar, a cadeia volta a conferir"
    assert con.execute("SELECT numero FROM ri_matriculas WHERE id=?",
                       (m,)).fetchone()["numero"] == "4014"


def test_renumerar_sincroniza_a_serie_inteira(con):
    m = matricula(con, 4011, "2")
    matricula(con, 4013, "2S")
    numeracao(con, "2", 4012, 4011)
    numeracao(con, "2S", 4014, 4013)
    RC.renumerar_matricula(con, m, 4014, agora=AGORA, motivo="Corrigindo a numeração")
    for livro in ("2", "2S"):
        linha = con.execute("SELECT * FROM ri_numeracao WHERE livro=?", (livro,)).fetchone()
        assert linha["proximo_numero"] == 4015, f"o volume {livro} tem de apontar para 4015"
        assert linha["maior_em_uso"] == 4014


def test_nao_renumera_para_numero_ocupado(con):
    m = matricula(con, 4011, "2")
    matricula(con, 4013, "2S")
    with pytest.raises(RC.CorrecaoError, match="já é da matrícula"):
        RC.renumerar_matricula(con, m, 4013, agora=AGORA, motivo="Tentativa indevida")


def test_nao_renumera_matricula_do_acervo(con):
    m = matricula(con, 582, "2C", origem="EOFICIO")
    with pytest.raises(RC.CorrecaoError, match="acervo"):
        RC.renumerar_matricula(con, m, 9999, agora=AGORA, motivo="Não pode mesmo")


def test_certidao_viva_impede_renumerar(con):
    m = matricula(con, 4011, "2")
    con.execute("""INSERT INTO ri_certidoes
                   (numero, ano, tipo, matricula_id, matricula_numero, data_emissao,
                    corpo, corpo_formato, cancelada, origem, emitida_em)
                   VALUES (7,2026,'INTEIRO_TEOR',?,'4011','2026-08-18','x','html',0,
                           'MANUAL',?)""", (m, AGORA))
    with pytest.raises(RC.CorrecaoError, match="certidão 7/2026"):
        RC.renumerar_matricula(con, m, 4014, agora=AGORA, motivo="Corrigindo a numeração")


def test_motivo_curto_recusado_na_renumeracao(con):
    m = matricula(con, 4011, "2")
    with pytest.raises(RC.CorrecaoError, match="dez letras"):
        RC.renumerar_matricula(con, m, 4014, agora=AGORA, motivo="erro")


def test_renumerar_para_o_mesmo_numero_e_recusado(con):
    m = matricula(con, 4011, "2")
    with pytest.raises(RC.CorrecaoError, match="já é a 4011"):
        RC.renumerar_matricula(con, m, 4011, agora=AGORA, motivo="Nada a fazer aqui")


# -------------------------------------------------------------------- partes


def parte(con, matricula_id, ato_id, nome, papel, doc=None, ativo=0):
    cur = con.execute(
        """INSERT INTO ri_partes
           (matricula_id, ato_id, nome, papel, documento_numero, documento_tipo,
            proprietario, proprietario_ativo, origem)
           VALUES (?,?,?,?,?,?,0,?,'MANUAL')""",
        (matricula_id, ato_id, nome, papel, doc,
         "CPF" if doc and len(doc) == 11 else "CNPJ" if doc else None, ativo))
    return int(cur.lastrowid)


@pytest.mark.parametrize("papel,esperado", [
    ("proprietário", True), ("adquirente", True), ("nu-proprietário", True),
    ("transmitente", False), ("outorgante", False), ("cônjuge", False),
    (None, False), ("", False),
])
def test_quem_o_papel_faz_titular(papel, esperado):
    assert RC.e_titular(papel) is esperado


def test_corrigir_o_papel_do_incra_e_da_adquirente(con):
    """O erro real do R-01: INCRA como adquirente, e a dona sem papel."""
    m = matricula(con, 4011, "2")
    a = ato(con, m, "R", 1, "4011", "R-01/4014")
    incra = parte(con, m, a, "INCRA", "adquirente", "00000013000160")
    maria = parte(con, m, a, "MARIA REGO SILVA PEREIRA", None, "00000002992")

    RC.corrigir_parte(con, incra, papel="transmitente", agora=AGORA,
                      motivo="O INCRA é o outorgante do título de domínio")
    RC.corrigir_parte(con, maria, papel="proprietário", agora=AGORA,
                      motivo="Adquirente do título de domínio; titular atual")

    linhas = {r["nome"]: r for r in con.execute("SELECT * FROM ri_partes")}
    assert linhas["INCRA"]["papel"] == "transmitente"
    assert linhas["INCRA"]["proprietario_ativo"] == 0
    assert linhas["MARIA REGO SILVA PEREIRA"]["papel"] == "proprietário"
    assert linhas["MARIA REGO SILVA PEREIRA"]["proprietario_ativo"] == 1, \
        "sem isto a certidão de propriedade sai vazia"


def test_documento_invalido_e_recusado(con):
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "ALGUEM", "proprietário")
    with pytest.raises(RC.CorrecaoError, match="dígitos"):
        RC.corrigir_parte(con, p, documento="123", agora=AGORA,
                          motivo="Tentando documento curto")


def test_documento_valido_marca_a_conferencia(con):
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "ALGUEM", "proprietário")
    RC.corrigir_parte(con, p, documento="000.000.029-92", agora=AGORA,
                      motivo="Documento conferido no título")
    linha = con.execute("SELECT * FROM ri_partes WHERE id=?", (p,)).fetchone()
    assert linha["documento_numero"] == "00000002992"
    assert linha["documento_tipo"] == "CPF"
    assert linha["documento_valido"] == 1


def test_titular_pode_ser_forcado_contra_o_papel(con):
    """Em permuta as duas pontas sao adquirentes, e nem toda vira dona de tudo."""
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "ALGUEM", "adquirente", ativo=1)
    RC.corrigir_parte(con, p, titular=False, agora=AGORA,
                      motivo="Permuta: adquiriu apenas fração já averbada")
    assert con.execute("SELECT proprietario_ativo FROM ri_partes WHERE id=?",
                       (p,)).fetchone()["proprietario_ativo"] == 0


def test_nada_alterado_e_recusado(con):
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "ALGUEM", "transmitente")
    with pytest.raises(RC.CorrecaoError, match="Nada foi alterado"):
        RC.corrigir_parte(con, p, papel="transmitente", agora=AGORA,
                          motivo="Não muda nada mesmo")


def test_nome_em_branco_e_recusado(con):
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "ALGUEM", "transmitente")
    with pytest.raises(RC.CorrecaoError, match="não pode ficar em branco"):
        RC.corrigir_parte(con, p, nome="   ", agora=AGORA, motivo="Nome apagado sem querer")


def test_o_de_para_fica_registrado(con):
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "INCRA", "adquirente")
    saida = RC.corrigir_parte(con, p, papel="transmitente", agora=AGORA,
                              motivo="O INCRA é quem transmite")
    assert saida["mudancas"]["papel"] == {"de": "adquirente", "para": "transmitente"}


def test_numero_provisorio_nao_entra_na_serie(con):
    """07/10/2026, «opção 2»: as fantasmas 904020–904023 faziam o próximo ser 904024."""
    for n in (4020, 4021):
        matricula(con, n, "2")
    for n in (904020, 904023):
        matricula(con, n, "2")
    numeracao(con, "2", 4022, 4021)
    assert RC.proximo_numero(con, "2") == 4022
