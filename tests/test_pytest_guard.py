from __future__ import annotations

from pathlib import Path

import pytest

from tools.pytest_guard import (
    TravaDaSuite,
    codigo_de_saida,
    diferencas,
    estado_da_arvore,
)


def test_retrato_detecta_alteracao_sem_contar_artefato(tmp_path: Path):
    codigo = tmp_path / "modulo.py"
    codigo.write_text("valor = 1\n", encoding="utf-8")
    antes = estado_da_arvore(tmp_path)
    codigo.write_text("valor = 200\n", encoding="utf-8")
    (tmp_path / "execucao.log").write_text("nao e fonte", encoding="utf-8")
    assert diferencas(antes, estado_da_arvore(tmp_path)) == ["modulo.py"]


def test_retrato_poda_cache_e_conserva_caminho_relativo(tmp_path: Path):
    fonte = tmp_path / "pacote" / "modulo.py"
    fonte.parent.mkdir()
    fonte.write_text("valor = 1\n", encoding="utf-8")
    cache = tmp_path / "__pycache__" / "tambem.py"
    cache.parent.mkdir()
    cache.write_text("nao vigiar\n", encoding="utf-8")
    assert set(estado_da_arvore(tmp_path)) == {"pacote/modulo.py"}


def test_a_segunda_suite_na_mesma_arvore_e_recusada(tmp_path: Path):
    primeira = TravaDaSuite(tmp_path)
    segunda = TravaDaSuite(tmp_path)
    primeira.adquirir()
    try:
        with pytest.raises(RuntimeError, match="outra suite pytest"):
            segunda.adquirir()
    finally:
        primeira.liberar()

    # A trava nao deixa lixo logico: a proxima execucao pode comecar.
    segunda.adquirir()
    segunda.liberar()


def test_arvore_alterada_nunca_devolve_sucesso():
    assert codigo_de_saida(0, arvore_invalidada=True) == 2
    assert codigo_de_saida(1, arvore_invalidada=True) == 1
    assert codigo_de_saida(0, arvore_invalidada=False) == 0
