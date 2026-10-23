"""Acervo RCPN: digitação/importação com poucos campos (pedido 18/09/2026).

Balcão novo (origem MANUAL) continua com a régua da Lei 6.015/1973.
Digitar do acervo (origem ACERVO) e importação RCPN aceitam registro esparso.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import importar_padrao as IMP                     # noqa: E402
import rc_assento as RC                          # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from rc_schema import init_rc_schema             # noqa: E402

AGORA = "2026-09-18T12:00:00"
EXTENSO = "dezoito de setembro de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFICIO UNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabeliao e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    return con


def test_manual_ainda_recusa_obito_sem_declarante():
    con = banco()
    with pytest.raises(RC.RcError, match="declarante"):
        RC.lavrar_assento(
            con, especie="OBITO", nome="ANTONIO DA SILVA", sv=SV,
            agora=AGORA, data_extenso=EXTENSO,
            data_fato="1980-01-01",
            termo_dados={"local_fato_nome": "Hospital"},
            ibge={"numero_do": "1"},
            origem="MANUAL",
            pessoas=[
                {"papel": "FALECIDO", "nome": "ANTONIO DA SILVA"},
                {"papel": "MAE", "nome": "IGNORADO"},
                {"papel": "PAI", "nome": "IGNORADO"},
            ])


def test_origem_acervo_lava_obito_so_com_nome():
    con = banco()
    r = RC.lavrar_assento(
        con, especie="OBITO", nome="ANTONIO DA SILVA", sv=SV,
        agora=AGORA, data_extenso=EXTENSO,
        origem="ACERVO",
        pessoas=[{"papel": "FALECIDO", "nome": "ANTONIO DA SILVA"}])
    assert r["assento_id"]
    row = con.execute(
        "SELECT origem, nome FROM rc_assentos WHERE id=?",
        (r["assento_id"],)).fetchone()
    assert row["origem"] == "ACERVO"
    assert row["nome"] == "ANTONIO DA SILVA"


def test_origem_acervo_lava_nascimento_esparso():
    con = banco()
    r = RC.lavrar_assento(
        con, especie="NASCIMENTO", nome="MARIA ANTIGA", sv=SV,
        agora=AGORA, data_extenso=EXTENSO,
        origem="ACERVO")
    assert r["assento_id"]
    assert r["serie"] == "RC_A"


def test_import_rcpn_sem_serie_deriva_e_aceita():
    con = banco()
    texto = __import__("json").dumps({
        "formato": IMP.FORMATO,
        "versao": 1,
        "especie": "RCPN_ASSENTO",
        "registros": [
            {"chave": "acervo-1", "especie": "OBITO", "nome": "JOSE VELHO"},
        ],
    })
    q = IMP.conferir(con, texto)
    assert q["entram"] and not q["recusados"]
    feito = IMP.importar(con, texto, agora=AGORA, por="teste")
    assert feito["entraram"] == 1
    row = con.execute(
        "SELECT serie, especie, nome, origem FROM rc_assentos").fetchone()
    assert row["serie"] == "RC_C"
    assert row["especie"] == "OBITO"
    assert row["nome"] == "JOSE VELHO"
    assert row["origem"] == "IMPORTACAO"
