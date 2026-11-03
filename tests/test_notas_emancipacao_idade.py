"""A emancipação confere a idade do emancipando antes de montar o teor.

Ensaio de atos das Notas, 03/11/2026 (docs/ensaio_de_atos/relatorio_notas.md, item 7): a minuta
afirma «portanto com dezesseis anos completos» de qualquer data digitada. CC art. 5º, par. ún., I
(dezesseis anos completos) e art. 5º, caput (aos dezoito, já é capaz). A prática pela tela está em
`test_ensaio_de_atos_notas`.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notas_teor as NT  # noqa: E402

HOJE = date(2026, 11, 3)
CAMPO = NT.CHAVE_NASCIMENTO_DO_EMANCIPANDO


def test_dezesseis_anos_completos_no_dia_passa():
    assert NT.recusa_da_emancipacao({CAMPO: "três de novembro de 2010 (03/11/2010)"}, HOJE) == ""


def test_um_dia_antes_dos_dezesseis_e_recusado():
    assert "15 ano(s)" in NT.recusa_da_emancipacao({CAMPO: "04/11/2010"}, HOJE)


def test_quem_ja_tem_dezoito_nao_se_emancipa():
    assert "já tem 18 anos" in NT.recusa_da_emancipacao({CAMPO: "2008-11-03"}, HOJE)


def test_a_data_sem_algarismos_e_pedida_com_eles():
    assert "dd/mm/aaaa" in NT.recusa_da_emancipacao({CAMPO: "dez de outubro de dois mil e dez"}, HOJE)


def test_data_que_nao_existe_e_recusada():
    assert "não existe" in NT.recusa_da_emancipacao({CAMPO: "31/02/2010"}, HOJE)


def test_outra_minuta_nao_e_conferida():
    assert NT.recusa_da_emancipacao({"data_do_itbi": "01/01/2026"}, HOJE) == ""
