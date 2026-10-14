"""
Testes da CARGA DO RAZAO DOS SELOS.

POR QUE ELA EXISTE
    O inventario do acervo, em 27/08/2026, achou o unico buraco de verdade da
    migracao: a carga do Protesto grava o numero do selo DENTRO do ato
    (`pt_atos.selo`), o que esta certo — mas o RAZAO, `sd_selos`, comecava
    VAZIO.

    Com o razao vazio, `registrar_selo_obtido_a_mao` nao tinha contra o que
    comparar: **um selo de 2023 podia ser digitado hoje como novo, e nada
    recusava.** A trava existia e nao tinha memoria.

O QUE ESTES TESTES GUARDAM
      - o selo entra uma vez so, e a carga e repetivel;
      - o que foi CANCELADO no E-Oficio entra cancelado;
      - o que foi obtido e nao usado entra sem `usado_em` — e e assim que ele
        aparece na tela de «selo obtido e nao usado»;
      - a amarracao ao ato e EXATA, pelo numero do selo, que e unico;
      - e a trava do selo repetido passa a ter memoria.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import acervo_carga as AC                            # noqa: E402
import ato_selado as AS                              # noqa: E402
from nucleo_schema import init_nucleo_schema         # noqa: E402
from pt_schema import init_pt_schema                 # noqa: E402
from selador_config import init_selador_schema       # noqa: E402

AGORA = "2026-08-27T19:00:00"
SELO_USADO = "APONTA000000ABCDEFGHIJKLMN01"
SELO_ORFAO = "PRENOT000000ZEZSIN46Y2QXQM16"
SELO_CANCELADO = "CERTID000000NNRLQN37MGQ9J507"


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    init_selador_schema(con)
    con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, situacao, origem,
               criado_em) VALUES ('DMI','84713/1','APONTADO','EOFICIO',?)""",
        (AGORA,))
    con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, selo, data_ato, origem,
               criado_em) VALUES (1,'APONTAMENTO',?,'2026-08-24','EOFICIO',?)""",
        (SELO_USADO, AGORA))
    return con


def acervo() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE tbSeloIndividual (
            intChave INTEGER, strSelo TEXT, strTextoSelo TEXT, strURLAto TEXT,
            dtmData TEXT, dtmdata_selo TEXT, bitUtilizado INTEGER,
            bitSeloCancelado INTEGER, strUserid_Selou TEXT);
    """)
    con.executemany(
        "INSERT INTO tbSeloIndividual VALUES (?,?,?,?,?,?,?,?,?)",
        [(1, SELO_USADO, "Poder Judiciário – TJMA.", "/selo/protesto/titulo",
          "2026-08-24 09:00:00", "2026-08-24 00:00:00", 1, 0, "CARLA"),
         (2, SELO_ORFAO, None, "/selo/imovel/prenotacao",
          "2026-08-17 11:50:12", "2026-08-17 00:00:00", 0, 0, "CARLA"),
         (3, SELO_CANCELADO, None, "/selo/civil/casamento/segunda-via",
          "2023-05-05 17:50:36", "2023-05-05 00:00:00", 1, 1, "DEBORA"),
         # Selo antigo, de antes de o E-Oficio guardar o caminho.
         (4, "REGNAS000000YTZDXEVME7PFT019", None, None,
          "2020-06-03 10:00:00", None, 1, 0, None),
         # Linha sem numero: nao e selo, e nao entra.
         (5, "   ", None, "/selo/protesto/titulo", "2020-01-01", None, 0, 0, None)])
    con.commit()
    return con


def test_o_razao_deixa_de_comecar_vazio():
    con = banco()
    r = AC.carregar_selos(con, acervo(), agora=AGORA)
    assert r.lidos == 4                 # a linha sem número não é selo
    assert r.inseridos == 4
    assert con.execute("SELECT COUNT(*) c FROM sd_selos").fetchone()["c"] == 4


def test_o_que_foi_cancelado_no_eoficio_entra_cancelado():
    con = banco()
    AC.carregar_selos(con, acervo(), agora=AGORA)
    linha = con.execute("SELECT * FROM sd_selos WHERE numero=?",
                        (SELO_CANCELADO,)).fetchone()
    assert linha["cancelado_em"] is not None
    assert "E-Ofício" in linha["motivo_cancelamento"]


def test_o_selo_obtido_e_nao_usado_entra_sem_uso():
    """São os 1.304 órfãos que o E-Ofício deixou — 5% de tudo o que a casa
    selou em seis anos. Eles continuam órfãos, e é assim que aparecem na tela
    de «selo obtido e não usado»."""
    con = banco()
    r = AC.carregar_selos(con, acervo(), agora=AGORA)
    linha = con.execute("SELECT * FROM sd_selos WHERE numero=?",
                        (SELO_ORFAO,)).fetchone()
    assert linha["usado_em"] is None and linha["ato_id"] is None
    assert r.contagens["obtidos_e_nao_usados"] == 1


def test_a_amarracao_ao_ato_e_exata_pelo_numero():
    """O número do selo é único — conferido: zero repetidos nos 26.130. Por
    isso a amarração não é aproximação: é igualdade."""
    con = banco()
    r = AC.carregar_selos(con, acervo(), agora=AGORA)
    linha = con.execute("SELECT * FROM sd_selos WHERE numero=?",
                        (SELO_USADO,)).fetchone()
    assert linha["tabela"] == "pt_atos" and linha["ato_id"] == 1
    assert linha["usado_em"] is not None
    assert r.contagens.get("amarrados_a_pt_atos") == 1


def test_selo_sem_caminho_entra_do_mesmo_jeito():
    """Os mais antigos foram gravados antes de o E-Ofício guardar o
    `strURLAto`. O que importa deles é o número."""
    con = banco()
    AC.carregar_selos(con, acervo(), agora=AGORA)
    linha = con.execute(
        "SELECT * FROM sd_selos WHERE numero LIKE 'REGNAS%'").fetchone()
    assert linha is not None
    assert linha["caminho"] is None and linha["atribuicao"] is None


def test_a_atribuicao_vem_do_caminho_e_e_a_palavra_do_selador():
    """Traduzi-la para «RCPN» aqui faria o razão histórico falar uma língua e o
    razão novo, outra."""
    con = banco()
    AC.carregar_selos(con, acervo(), agora=AGORA)
    assert con.execute("SELECT atribuicao FROM sd_selos WHERE numero=?",
                       (SELO_CANCELADO,)).fetchone()[0] == "CIVIL"
    assert con.execute("SELECT atribuicao FROM sd_selos WHERE numero=?",
                       (SELO_ORFAO,)).fetchone()[0] == "IMOVEL"


def test_a_carga_dos_selos_e_repetivel():
    con = banco()
    velho = acervo()
    AC.carregar_selos(con, velho, agora=AGORA)
    de_novo = AC.carregar_selos(con, velho, agora=AGORA)
    assert de_novo.inseridos == 0
    assert de_novo.repetidos == 4
    assert con.execute("SELECT COUNT(*) c FROM sd_selos").fetchone()["c"] == 4


def test_a_TRAVA_DO_SELO_REPETIDO_passa_a_ter_memoria():
    """É POR ISTO QUE A CARGA EXISTE.

    Antes dela, um selo de 2023 podia ser digitado hoje como novo e nada
    recusava — a trava existia e não tinha contra o que comparar.
    """
    con = banco()
    AC.carregar_selos(con, acervo(), agora=AGORA)
    con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem, criado_em)
           VALUES (1,'PROTESTO','2026-08-27','MANUAL',?)""", (AGORA,))
    novo_ato = con.execute("SELECT MAX(id) FROM pt_atos").fetchone()[0]
    with pytest.raises(AS.AtoError) as erro:
        AS.registrar_selo_obtido_a_mao(
            con, SELO_USADO, tabela="pt_atos", ato_id=novo_ato,
            atribuicao="PROTESTO", agora=AGORA, cns="000000")
    assert "já" in str(erro.value).lower()


def test_a_carga_dos_selos_e_a_ultima_da_fila():
    """Ela se amarra aos atos que as cargas anteriores acabaram de trazer."""
    assert list(AC.CARGAS)[-1] == "selos"
