"""Certidao negativa de imovel — busca sem achado (#Beatriz 25/09/2026)."""
from __future__ import annotations

import sqlite3

import ato_selado as AS
import modelos_da_casa as MODELOS
import ri_certidao_negativa as RINEG
import ri_schema as RS
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402


def test_tipo_nao_esta_na_tela_da_matricula():
    """#75: negativa de imovel nao volta ao seletor da ficha."""
    assert RINEG.TIPO not in RS.TIPOS_CERTIDAO
    assert RINEG.TIPO in RS.ROTULOS_CERTIDAO_RI


def test_selo_usa_item_medido_nao_inventado():
    assert RINEG.TIPO not in AS.CODIGO_DA_CERTIDAO_DO_RI
    assert AS.CODIGO_DA_CERTIDAO_NEGATIVA_DE_IMOVEL == "16.24.1"
    assert AS.itens_da_certidao_do_ri(RINEG.TIPO, 1) == [("16.24.1", 1)]
    assert AS.itens_da_certidao_do_ri(RINEG.TIPO, 3) == [
        ("16.24.1", 1), ("16.24.2", 2)]


def test_modelo_no_catalogo():
    assert any(c["chave"] == RINEG.CHAVE_MODELO for c in MODELOS.CATALOGO)


def test_recusa_quando_busca_acha():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.executescript(
        """
        CREATE TABLE ri_matriculas (id INTEGER PRIMARY KEY, numero TEXT,
            logradouro TEXT, bairro TEXT, imovel_norm TEXT, rural_urbano TEXT,
            cnm TEXT);
        CREATE TABLE ri_partes (id INTEGER PRIMARY KEY, matricula_id INTEGER,
            nome TEXT, nome_norm TEXT, documento_numero TEXT,
            documento_tipo TEXT, documento_valido INTEGER,
            qualificacao TEXT, proprietario_ativo INTEGER, papel TEXT);
        INSERT INTO ri_matriculas VALUES (1,'1','Rua A','Centro','rua a', 'U', NULL);
        INSERT INTO ri_partes VALUES (1,1,'FULANO TESTE','fulano teste','123',
            'CPF',1,'',1,'PROPRIETARIO');
        """
    )
    ach = RINEG.buscar_por_pessoa(con, "FULANO")
    assert len(ach) == 1
    try:
        RINEG.conferir_negativa(ach)
        assert False, "deveria recusar"
    except RINEG.CertidaoNegativaError:
        pass
    vazia = RINEG.buscar_por_pessoa(con, "NOME QUE NAO EXISTE XYZ")
    assert vazia == []
    RINEG.conferir_negativa(vazia)


def test_modelo_sem_traco_de_assinatura():
    assert "________" not in RINEG.MODELO_PADRAO
    limpo = RINEG.limpar_corpo("Nome\n____________________\nCargo")
    assert "____" not in limpo


def test_matricula_de_numero_sem_digito_abre_a_lista_como_no_sqlite():
    """O CAST do SQLite dava 0 para numero sem digito, e essas matriculas
    abriam a lista. Sem o coalesce, o PostgreSQL as manda para o fim -- e,
    passando de 60 achados, para fora do corte."""
    con = conexao_de_teste()
    con.executescript(
        """
        CREATE TABLE ri_matriculas (id INTEGER PRIMARY KEY, numero TEXT,
            logradouro TEXT, bairro TEXT, imovel_norm TEXT, rural_urbano TEXT,
            cnm TEXT);
        INSERT INTO ri_matriculas VALUES (1,'12','Rua A','Centro','RUA A','U',NULL);
        INSERT INTO ri_matriculas VALUES (2,'S/N','Rua A','Centro','RUA A','U',NULL);
        INSERT INTO ri_matriculas VALUES (3,'3','Rua A','Centro','RUA A','U',NULL);
        """
    )
    achados = RINEG.buscar_por_imovel(con, "rua a")
    assert [m["numero"] for m in achados] == ["S/N", "3", "12"]
