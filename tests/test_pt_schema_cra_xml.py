"""Migração aditiva da identidade da remessa XML; não recebe títulos."""
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema


def _colunas(con):
    return {r[1] for r in con.execute("PRAGMA table_info(pt_remessas)")}


def test_banco_novo_tem_identidade_xml_e_indice_unico():
    con = conexao_de_teste()
    # `pt_atos.livro_id` aponta para `nu_livros`, e o PostgreSQL nativo
    # cobra a chave estrangeira ja na criacao: o nucleo vem antes.
    init_nucleo_schema(con)
    init_pt_schema(con)
    assert {"origem_xml_ambiente", "origem_xml_hash_lote",
            "origem_xml_chave"} <= _colunas(con)
    indices = {r[1] for r in con.execute("PRAGMA index_list(pt_remessas)")}
    assert "ux_pt_remessas_xml_chave" in indices
    con.close()


def test_banco_legado_migra_sem_afetar_txt_e_trava_xml_duplicado():
    con = conexao_de_teste()
    con.execute("""CREATE TABLE pt_remessas (
        id INTEGER PRIMARY KEY, tipo TEXT NOT NULL,
        apresentante_codigo TEXT NOT NULL, dia TEXT NOT NULL,
        conteudo TEXT NOT NULL, hash_arquivo TEXT NOT NULL,
        recebida_em TEXT NOT NULL)""")
    con.execute("""INSERT INTO pt_remessas
        (tipo, apresentante_codigo, dia, conteudo, hash_arquivo, recebida_em)
        VALUES ('BFOSDTTPR','001','2026-09-01','txt1','hash-txt-1','2026-09-01')""")
    # `pt_atos.livro_id` aponta para `nu_livros`, e o PostgreSQL nativo
    # cobra a chave estrangeira ja na criacao: o nucleo vem antes.
    init_nucleo_schema(con)
    init_pt_schema(con)
    init_pt_schema(con)  # inicialização repetida não perde nem duplica colunas
    assert con.execute("SELECT COUNT(*) FROM pt_remessas").fetchone()[0] == 1
    assert con.execute("SELECT origem_xml_chave FROM pt_remessas").fetchone()[0] is None

    con.execute("""INSERT INTO pt_remessas
        (tipo, apresentante_codigo, dia, conteudo, hash_arquivo, recebida_em,
         origem_xml_ambiente, origem_xml_hash_lote, origem_xml_chave)
        VALUES ('BFOSDTTPR','001','2026-09-02','xml1','hash-xml-1','2026-09-02',
                'HOMOLOGACAO','lote-a','chave-a')""")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("""INSERT INTO pt_remessas
            (tipo, apresentante_codigo, dia, conteudo, hash_arquivo, recebida_em,
             origem_xml_ambiente, origem_xml_hash_lote, origem_xml_chave)
            VALUES ('BFOSDTTPR','001','2026-09-02','xml2','hash-xml-2','2026-09-02',
                    'HOMOLOGACAO','lote-a','chave-a')""")
    con.close()
