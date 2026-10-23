"""Requisitos legais da lavratura — Lei nº 6.015/1973.

O oficial, em 01/09/2026: o servidor recusa assento sem cumprimento aos
requisitos. O formulário pode DECLARAR que não tem a informação (ignorado);
não se lavra em branco o que a lei dispõe. Branco não é declaração.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_assento as RC                          # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from rc_schema import init_rc_schema             # noqa: E402

AGORA = "2026-09-01T10:00:00"
EXTENSO = "primeiro dia do mês de setembro do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    return con


def pessoas_nascimento(nome="JOAO DA SILVA", mae="MARIA DA SILVA",
                       pai="IGNORADO", declarante="MARIA DA SILVA"):
    return [
        {"papel": "REGISTRADO", "nome": nome, "sexo": "M"},
        {"papel": "MAE", "nome": mae},
        {"papel": "PAI", "nome": pai},
        {"papel": "DECLARANTE", "nome": declarante},
    ]


def test_nascimento_sem_nome_e_recusado():
    con = banco()
    with pytest.raises(RC.RcError, match="nome de quem é o registro"):
        RC.lavrar_assento(
            con, especie="NASCIMENTO", nome="   ", sv=SV,
            agora=AGORA, data_extenso=EXTENSO,
            data_fato="2026-08-20", dados={"sexo": "M"},
            termo_dados={"local_fato_nome": "Hospital Municipal"},
            pessoas=pessoas_nascimento(nome=""))


def test_nascimento_com_mae_em_branco_e_recusado():
    con = banco()
    with pytest.raises(RC.RcError, match="filiação 1"):
        RC.lavrar_assento(
            con, especie="NASCIMENTO", nome="JOAO DA SILVA", sv=SV,
            agora=AGORA, data_extenso=EXTENSO,
            data_fato="2026-08-20", dados={"sexo": "M"},
            termo_dados={"local_fato_nome": "Hospital Municipal"},
            pessoas=pessoas_nascimento(mae=""))


def test_nascimento_com_mae_declarada_ignorada_lavra():
    con = banco()
    r = RC.lavrar_assento(
        con, especie="NASCIMENTO", nome="JOAO DA SILVA", sv=SV,
        agora=AGORA, data_extenso=EXTENSO,
        data_fato="2026-08-20", dados={"sexo": "M"},
        termo_dados={"local_fato_nome": "Hospital Municipal"},
        ibge={"local_nascimento": 1},        # relato #130: o SIRC exige
        pessoas=pessoas_nascimento(mae="IGNORADO"))
    assert r["assento_id"]
    mae = con.execute(
        "SELECT nome FROM rc_pessoas WHERE assento_id=? AND papel='MAE'",
        (r["assento_id"],)).fetchone()
    assert mae["nome"] == "IGNORADO"


def test_nascimento_com_pai_nao_tem_lavra():
    """«não tem» é a mesma declaração que ignorado — não é branco."""
    con = banco()
    r = RC.lavrar_assento(
        con, especie="NASCIMENTO", nome="JOAO DA SILVA", sv=SV,
        agora=AGORA, data_extenso=EXTENSO,
        data_fato="2026-08-20", dados={"sexo": "M"},
        termo_dados={"local_fato_nome": "Hospital Municipal"},
        ibge={"local_nascimento": 1},        # relato #130: o SIRC exige
        pessoas=pessoas_nascimento(pai="não tem"))
    assert r["serie"] == "RC_A"


def test_casamento_sem_nubentes_e_recusado():
    con = banco()
    with pytest.raises(RC.RcError, match="nubente"):
        RC.lavrar_assento(
            con, especie="CASAMENTO", nome="A E B", sv=SV,
            agora=AGORA, data_extenso=EXTENSO,
            data_fato="2026-08-20", regime_bens="COMUNHAO_PARCIAL")


def test_obito_sem_nome_do_falecido_e_recusado():
    con = banco()
    with pytest.raises(RC.RcError, match="nome de quem é o registro"):
        RC.lavrar_assento(
            con, especie="OBITO", nome="  ", sv=SV,
            agora=AGORA, data_extenso=EXTENSO,
            data_fato="2026-08-01",
            termo_dados={"local_fato_nome": "Hospital Municipal"},
            ibge={"numero_do": "12345"},
            pessoas=[
                {"papel": "FALECIDO", "nome": ""},
                {"papel": "MAE", "nome": "IGNORADO"},
                {"papel": "PAI", "nome": "IGNORADO"},
                {"papel": "DECLARANTE", "nome": "FULANO"},
            ])


def test_a_recusa_lista_tudo_que_faltou():
    with pytest.raises(RC.RcError) as erro:
        RC.conferir_requisitos_legais("NASCIMENTO", {}, [])
    texto = str(erro.value)
    assert "Não se lavra o assento em branco" in texto
    assert "data do nascimento" in texto
    assert "sexo" in texto
    assert "declarante" in texto
    assert "vazio não é declaração" in texto


def test_carga_do_acervo_nao_e_recusada_por_campo_antigo_em_branco():
    """O papel já está no livro. Recusar a carga seria perder o acervo."""
    con = banco()
    r = RC.lavrar_assento(
        con, especie="NASCIMENTO", nome="JOAO ANTIGO", sv=SV,
        agora=AGORA, data_extenso=EXTENSO, origem="EOFICIO",
        origem_chave="ACERVO:1")
    assert r["assento_id"]
