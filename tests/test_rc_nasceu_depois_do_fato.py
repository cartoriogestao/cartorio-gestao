"""Quem age no registro pode ter nascido depois do fato — o ensaio de atos, 01/11/2026.

O PEDIDO do oficial: «antecipar esses problemas e processar antes de encontrar na prática». O ensaio
de atos (`tests/ensaio_de_atos_rcpn.py`) teve recusados pela tela dois atos que o balcão faz:

    - o nascimento tardio de 1990 com uma testemunha de 30 anos, que conhece a registrada adulta e
      atesta a identidade dela (LRP art. 46; CN-MA art. 249);
    - o óbito de 1985 declarado pelo neto, nascido em 1990.

A régua era a data do fato para toda pessoa do assento. O declarante, e no nascimento as testemunhas
DO ASSENTO (LRP art. 54, 9º), passam a ter a data do registro; pais, avós, nubentes e as testemunhas
que presenciaram o fato (o casamento, CC art. 1.534; a morte, LRP art. 77) continuam na do fato.

Os nomes são fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_assento as RC                          # noqa: E402
import rc_conferencia_dados as CD                # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from rc_schema import init_rc_schema             # noqa: E402

AGORA = "2026-10-09T10:00:00"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS", "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


@pytest.mark.parametrize("papel, especie, esperado", [
    ("DECLARANTE", "NASCIMENTO", "2026-11-02"),
    ("DECLARANTE", "OBITO", "2026-11-02"),
    ("TESTEMUNHA", "NASCIMENTO", "2026-11-02"),
    ("TESTEMUNHA2", "NASCIMENTO", "2026-11-02"),
    ("MAE", "NASCIMENTO", "1990-06-15"),
    ("TESTEMUNHA", "OBITO", "1990-06-15"),
    ("TESTEMUNHA", "CASAMENTO", "1990-06-15"),
    ("NUBENTE1", "CASAMENTO", "1990-06-15"),
])
def test_o_limite_e_o_registro_para_quem_age_nele_e_o_fato_para_o_resto(papel, especie, esperado):
    assert RC.limite_do_nascimento(papel, especie, "1990-06-15", "2026-11-02T10:00:00") == esperado


def _tardio(*gente) -> dict:
    return {"especie": "NASCIMENTO", "nome": "ANA EXEMPLO DE SOUZA", "data_fato": "1990-06-15",
            "data_ato": "2026-11-02T10:00:00", "teor": "", "pessoas": [
                {"papel": "REGISTRADO", "nome": "ANA EXEMPLO DE SOUZA", "sexo": "F",
                 "data_nascimento": "1990-06-15"},
                {"papel": "MAE", "nome": "BEATRIZ EXEMPLO DE SOUZA", "sexo": "F",
                 "data_nascimento": "1962-03-10"}, *gente]}


def _travas(dados: dict) -> list[str]:
    return [p["mensagem"] for p in CD.bloqueios(CD.conferir(dados)) if p["codigo"] == "NASCEU_DEPOIS_DO_FATO"]


def test_no_tardio_a_testemunha_mais_nova_que_a_registrada_nao_trava():
    assert not _travas(_tardio({"papel": "TESTEMUNHA", "nome": "CARLA EXEMPLO TESTEMUNHA",
                                "data_nascimento": "1996-03-10"},
                               {"papel": "TESTEMUNHA2", "nome": "JOAO EXEMPLO TESTEMUNHA",
                                "data_nascimento": "1998-01-01"}))


def test_o_declarante_nascido_depois_do_registro_ainda_trava():
    trava = _travas(_tardio({"papel": "DECLARANTE", "nome": "CARLA EXEMPLO DECLARANTE",
                             "data_nascimento": "2026-12-01"}))
    assert trava and "depois do registro (02/11/2026)" in trava[0]


def test_a_mae_nascida_depois_do_parto_ainda_trava():
    dados = _tardio()
    dados["pessoas"][1]["data_nascimento"] = "1996-03-10"
    trava = _travas(dados)
    assert trava and "depois do fato (15/06/1990)" in trava[0]


def test_no_obito_o_neto_declara_e_a_testemunha_da_morte_nao_pode_ser_mais_nova():
    obito = {"especie": "OBITO", "nome": "JOSE EXEMPLO AVO", "data_fato": "1985-03-01",
             "data_ato": "2026-11-02T10:00:00", "teor": "", "pessoas": [
                 {"papel": "FALECIDO", "nome": "JOSE EXEMPLO AVO", "data_nascimento": "1920-01-02"},
                 {"papel": "DECLARANTE", "nome": "PEDRO EXEMPLO NETO", "data_nascimento": "1990-07-07"}]}
    assert not _travas(obito)
    obito["pessoas"].append({"papel": "TESTEMUNHA", "nome": "CARLA EXEMPLO", "data_nascimento": "1990-07-07"})
    assert _travas(obito)


def _banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    return con


def _nascimento(con) -> int:
    return RC.lavrar_assento(
        con, especie="NASCIMENTO", nome="JOÃO EXEMPLO DA SILVA", sv=SV, agora=AGORA,
        data_extenso="nove dias do mês de outubro do ano de dois mil e vinte e seis",
        data_fato="2026-10-01", dados={"sexo": "M"}, teor="",
        ibge={"dnv": "30-12345678-9", "local_nascimento": 1},
        termo_dados={"local_fato_nome": "Hospital Municipal", "hora_fato": "08:46"},
        pessoas=[{"papel": "REGISTRADO", "nome": "JOÃO EXEMPLO DA SILVA", "sexo": "M"},
                 {"papel": "MAE", "nome": "MARIA EXEMPLO DA SILVA", "sexo": "F"},
                 {"papel": "PAI", "nome": "JOSÉ EXEMPLO DA SILVA", "sexo": "M"},
                 {"papel": "DECLARANTE", "nome": "MARIA EXEMPLO DA SILVA", "sexo": "F"}])["assento_id"]


def test_a_gravacao_da_pessoa_segue_a_mesma_regua():
    """`registrar_pessoa` é por onde a tela grava cada pessoa: era ali a recusa que o ensaio viu."""
    con = _banco()
    aid = _nascimento(con)
    RC.registrar_pessoa(con, aid, papel="TESTEMUNHA", especie="NASCIMENTO", agora=AGORA,
                        nome="CARLA EXEMPLO TESTEMUNHA", data_nascimento="2026-10-05")
    with pytest.raises(RC.RcError, match="posterior ao próprio ato"):
        RC.registrar_pessoa(con, aid, papel="TESTEMUNHA", especie="NASCIMENTO", agora=AGORA,
                            nome="JOAO EXEMPLO TESTEMUNHA", data_nascimento="2026-10-20")
    with pytest.raises(RC.RcError, match="posterior ao próprio ato"):
        RC.registrar_pessoa(con, aid, papel="AVO_MATERNA", especie="NASCIMENTO", agora=AGORA,
                            nome="ANA EXEMPLO AVO", data_nascimento="2026-10-05")
