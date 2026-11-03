"""O que a CESDI pede do divórcio e do inventário sai da tela do ato.

Ensaio de atos das Notas, item 14 (decisão do oficial, 03/11/2026): todo divórcio e todo inventário
paravam na remessa da CESDI — a qualidade de cada parte, a data do casamento, o regime e o responsável
pelos menores não tinham onde ser ditos. A prática pela tela está em `test_ensaio_de_atos_notas`. Os
nomes são fictícios.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notas_censec as NC  # noqa: E402
import notas_teor as NT  # noqa: E402


@pytest.mark.parametrize("qualificacao,qualidade", [
    ("ADVOGADO", "Advogado"), ("Advogada", "Advogado"), ("AUTOR DA HERANÇA", "Falecido"),
    ("HERDEIRA", "Herdeiro"), ("INVENTARIANTE", "Inventariante"), ("VIÚVA MEEIRA", "Viuvo"),
    ("DIVORCIANDA", "Divorciando"), ("SEPARANDO", "Separando"), ("CESSIONÁRIA", "CessionarioAdjudicatarios"),
    ("OUTORGANTE", None),
])
def test_a_qualidade_da_cesdi_sai_da_qualificacao(qualificacao, qualidade):
    assert NC.qualidade_cesdi_da_qualificacao(qualificacao) == qualidade


def test_o_falecido_nao_comparece_nem_assina():
    partes = [{"id": 1, "nome": "JOSE EXEMPLO DOS SANTOS", "qualificacao": "AUTOR DA HERANÇA"},
              {"id": 2, "nome": "ANA EXEMPLO HERDEIRA", "qualificacao": "HERDEIRA"}]
    outorgantes, _ = NT.partes_por_lado(partes, tipo_ato="ESCRITURA")
    assert "JOSE" not in outorgantes and "ANA EXEMPLO HERDEIRA" in outorgantes
    assert "JOSE" not in NT.texto_dos_assinantes(partes)


def test_a_data_do_casamento_e_o_regime_vem_da_minuta():
    assert NT.dados_da_cesdi_da_minuta({"data_do_casamento": "dez de maio de 2000 (10/05/2000)",
                                         "regime_de_bens": "comunhão parcial de bens"}) == {
        "casamento_data": "2000-05-10", "regime_bens": "COMUNHÃO PARCIAL DE BENS"}
    assert NC.regime_bens_censec("COMUNHÃO PARCIAL DE BENS") == "ComunhaoParcial"
    assert NT.dados_da_cesdi_da_minuta({"data_do_casamento": "sem data"}) == {}
