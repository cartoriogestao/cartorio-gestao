from __future__ import annotations

from pathlib import Path

import pytest

from tools import rodar_suite


@pytest.mark.parametrize(("processadores", "esperado"), [
    (2, 2), (4, 2), (8, 4), (12, 6), (32, 6),
])
def test_o_paralelismo_e_conservador(processadores, esperado):
    assert rodar_suite.trabalhadores_padrao(processadores) == esperado


def test_o_numero_de_trabalhadores_pode_ser_medido_sem_editar(monkeypatch):
    monkeypatch.setenv("CARTORIO_TEST_WORKERS", "3")
    assert rodar_suite.trabalhadores() == 3


def test_override_invalido_falha_com_motivo(monkeypatch):
    monkeypatch.setenv("CARTORIO_TEST_WORKERS", "zero")
    with pytest.raises(SystemExit, match="inteiro positivo"):
        rodar_suite.trabalhadores()


def test_os_atalhos_devolvem_o_resultado_real_do_pytest():
    raiz = Path(__file__).resolve().parent.parent
    for nome in ("RODAR_SUITE_RAPIDA.cmd", "RODAR_SUITE_COMPLETA.cmd"):
        texto = (raiz / nome).read_text(encoding="utf-8")
        assert 'set "CODIGO=%ERRORLEVEL%"' in texto
        assert "endlocal & exit /b %CODIGO%" in texto
