"""A averbação que muda a filiação ou o nome muda a certidão, e o reconhecimento não se transcreve.

Decisão do oficial, 02/11/2026 (ensaio de atos, item 1). Depois do reconhecimento de paternidade, o breve
relato saía com «FILIAÇÃO: IGNORADO», os avós paternos «ND», o nome antigo — e transcrevia «… reconhece
como sua filha …» (Lei 8.560/1992, art. 6º; LRP art. 19, § 3º). O inteiro teor desse assento só sai por
autorização judicial (art. 6º, § 2º): isso a rota cobra, e o ensaio de atos confere pela tela.

Os nomes são fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_assento as RC                          # noqa: E402
import rc_certidao as RCE                        # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from rc_schema import init_rc_schema             # noqa: E402

AGORA = "2026-10-09T10:00:00"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS", "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


def _so_com_a_mae() -> tuple[sqlite3.Connection, int]:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    r = RC.lavrar_assento(
        con, especie="NASCIMENTO", nome="ANA EXEMPLO DE SOUZA", sv=SV, agora=AGORA,
        data_extenso="nove dias do mês de outubro do ano de dois mil e vinte e seis", data_fato="2026-10-01",
        dados={"sexo": "F"}, teor="", origem="ACERVO",
        pessoas=[{"papel": "REGISTRADO", "nome": "ANA EXEMPLO DE SOUZA", "sexo": "F"},
                 {"papel": "MAE", "nome": "BEATRIZ EXEMPLO DE SOUZA", "sexo": "F"},
                 {"papel": "PAI", "nome": "IGNORADO", "sexo": "M"}])
    return con, int(r["assento_id"])


def _papel(con, aid: int, papel: str) -> list[str]:
    return [r[0] for r in con.execute("SELECT nome FROM rc_pessoas WHERE assento_id=? AND papel=?", (aid, papel))]


def test_o_reconhecimento_troca_o_pai_poe_os_avos_e_o_nome_novo():
    con, aid = _so_com_a_mae()
    mudou = RC.atualizar_pela_averbacao(con, aid, agora=AGORA, novo_nome="ANA EXEMPLO DOS SANTOS",
                                        pai="MARIO EXEMPLO DOS SANTOS", avo_paterno="JOAO EXEMPLO DOS SANTOS",
                                        avo_paterna="MARIA EXEMPLO DOS SANTOS")
    assert mudou == ["nome", "PAI", "AVO_PATERNO", "AVO_PATERNA"]
    assert _papel(con, aid, "PAI") == ["MARIO EXEMPLO DOS SANTOS"]
    assert _papel(con, aid, "AVO_PATERNA") == ["MARIA EXEMPLO DOS SANTOS"]
    assert _papel(con, aid, "REGISTRADO") == ["ANA EXEMPLO DOS SANTOS"]
    assert con.execute("SELECT nome FROM rc_assentos WHERE id=?", (aid,)).fetchone()[0] == "ANA EXEMPLO DOS SANTOS"


def test_sem_campo_nada_muda():
    con, aid = _so_com_a_mae()
    assert RC.atualizar_pela_averbacao(con, aid, agora=AGORA) == []
    assert _papel(con, aid, "PAI") == ["IGNORADO"]


def test_a_natureza_fica_no_ato_e_o_reconhecimento_e_sigiloso():
    con, aid = _so_com_a_mae()
    assert not RC.tem_averbacao_sigilosa(con, aid)
    RC.averbar(con, aid, teor="Averbo a alteração do nome.", agora=AGORA, natureza="alteracao_nome")
    assert not RC.tem_averbacao_sigilosa(con, aid)
    RC.averbar(con, aid, teor="Averbo o reconhecimento.", agora=AGORA, natureza="reconhecimento_filiacao")
    assert RC.tem_averbacao_sigilosa(con, aid)
    naturezas = [r[0] for r in con.execute("SELECT natureza FROM rc_atos WHERE assento_id=? AND tipo='AVERBACAO'"
                                           " ORDER BY id", (aid,))]
    assert naturezas == ["alteracao_nome", "reconhecimento_filiacao"]


def test_a_certidao_menciona_o_reconhecimento_pela_inscricao_e_nao_o_transcreve():
    sigiloso = {"tipo": "AVERBACAO", "teor": "… reconhece como sua filha …", "natureza": "reconhecimento_filiacao"}
    comum = {"tipo": "AVERBACAO", "teor": "Averbo a alteração do nome.", "natureza": "alteracao_nome"}
    assert not RCE.se_transcreve(sigiloso) and RCE.se_transcreve(comum)
    assert RCE.alteracoes_fora_da_certidao([sigiloso, comum]) == [sigiloso]
