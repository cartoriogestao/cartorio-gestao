"""A qualificação no feminino vale o mesmo que no masculino — na CEP, no teor e na DOI.

Ensaio de atos das Notas, 03/11/2026 (docs/ensaio_de_atos/relatorio_notas.md, item 13): a doação de
uma «DOADORA» a uma «DONATARIA» era recusada pela trava da CEP e ficava sem outorgada no teor, e na DOI
«OUTORGADA», «DONATARIA» e «CESSIONARIA» caíam em dúvida. CC art. 215, § 1º, III. A prática pela tela
está em `test_ensaio_de_atos_notas`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notas_censec as NC  # noqa: E402
import notas_doi as NDOI  # noqa: E402
import notas_teor as NT  # noqa: E402

PARES = [("DOADOR", "DOADORA"), ("DONATARIO", "DONATARIA"), ("CESSIONARIO", "CESSIONARIA"),
         ("USUFRUTUARIO", "USUFRUTUARIA"), ("CREDOR", "CREDORA"), ("REQUERIDO", "REQUERIDA"),
         ("CONCILIADOR", "CONCILIADORA"), ("MEDIADOR", "MEDIADORA"), ("OUTORGADO", "OUTORGADA"),
         ("VENDEDOR", "VENDEDORA"), ("COMPRADOR", "COMPRADORA")]


@pytest.mark.parametrize("masculino,feminino", PARES)
def test_a_cep_le_o_feminino_como_o_masculino(masculino, feminino):
    assert NC.qualidade_cep(feminino) == NC.qualidade_cep(masculino) is not None


@pytest.mark.parametrize("masculino,feminino", PARES)
def test_o_teor_poe_o_feminino_do_mesmo_lado(masculino, feminino):
    assert NT.lado_da_parte({"qualificacao": feminino}, "ESCRITURA") == \
        NT.lado_da_parte({"qualificacao": masculino}, "ESCRITURA")


@pytest.mark.parametrize("masculino,feminino", [("DOADOR", "DOADORA"), ("DONATARIO", "DONATARIA"),
                                                ("CESSIONARIO", "CESSIONARIA"), ("OUTORGADO", "OUTORGADA"),
                                                ("VENDEDOR", "VENDEDORA"), ("COMPRADOR", "COMPRADORA")])
def test_a_doi_poe_o_feminino_do_mesmo_lado(masculino, feminino):
    assert NDOI.lado_da_parte(feminino) == NDOI.lado_da_parte(masculino) != "DUVIDA"


def test_a_doacao_da_doadora_a_donataria_tem_os_dois_lados_no_teor():
    outorgantes, outorgados = NT.partes_por_lado(
        [{"nome": "JOANA EXEMPLO DOS SANTOS", "qualificacao": "DOADORA"},
         {"nome": "BEATRIZ EXEMPLO DE SOUZA", "qualificacao": "DONATARIA"}], tipo_ato="ESCRITURA")
    assert "JOANA" in outorgantes and "BEATRIZ" in outorgados and "QUALIFIQUE" not in outorgados
