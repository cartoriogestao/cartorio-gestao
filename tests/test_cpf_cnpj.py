# -*- coding: utf-8 -*-
import cpf_cnpj as DOC


def test_cpf_certo():
    assert DOC.cpf_valido("000.000.045-02") is True
    assert DOC.cpf_valido("00000004502") is True
    assert DOC.documento_valido("000.000.045-02") is True


def test_cpf_digito_trocado():
    assert DOC.cpf_valido("13672050343") is False
    assert DOC.documento_valido("13672050343") is False


def test_cpf_todos_iguais():
    for n in range(10):
        assert DOC.cpf_valido(str(n) * 11) is False


def test_cpf_tamanho():
    assert DOC.cpf_valido("123") is False
    assert DOC.documento_valido("") is None
    assert DOC.documento_valido(None) is None


def test_cnpj_certo():
    # CNPJ valido de exemplo (Receita / calculadoras publicas)
    assert DOC.cnpj_valido("00.000.041/0001-88") is True
    assert DOC.documento_valido("00000041000188") is True


def test_cnpj_falso():
    assert DOC.cnpj_valido("11.222.333/0001-82") is False


def test_formatar():
    assert DOC.formatar_cpf("00000004502") == "000.000.045-02"
    assert DOC.formatar_documento("00000004502").count(".") == 2


def test_mensagem():
    msg = DOC.mensagem_documento_invalido("13672050343")
    assert "digito verificador" in msg
    assert "136.720.503-43" in msg


def test_duplicatas(tmp_path):
    import sqlite3
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE pessoas(id INTEGER PRIMARY KEY, documento TEXT, nome TEXT)")
    con.execute("INSERT INTO pessoas(documento, nome) VALUES (?,?)", ("00000004502", "Ana"))
    ach = DOC.buscar_duplicatas_por_documento(con, "pessoas", "documento", "000.000.045-02")
    assert len(ach) == 1
    assert ach[0]["nome"] == "Ana"
    vaz = DOC.buscar_duplicatas_por_documento(con, "pessoas", "documento", "000.000.045-02", excluir_id=1)
    assert vaz == []
