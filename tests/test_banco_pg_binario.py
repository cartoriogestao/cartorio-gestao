"""Quem acha o `pg_dump`: o processo da automação nasce sem `CG_PG_BIN` e sem o
PostgreSQL no PATH.

O QUE ESTES TESTES PROVAM (30/10/2026)
    O BACKUP_DIARIO caía em ERRO desde 28/10/2026 com «pg_dump não encontrado»,
    com o binário no disco: `binario_do_postgres` só olhava a variável e o PATH.
    Agora ele acha sozinho na pasta de instalação, sem que a variável e o PATH
    percam a precedência. Nenhum destes testes toca em banco.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import banco_pg  # noqa: E402

ARQUIVO = "pg_dump.exe" if os.name == "nt" else "pg_dump"


def _instalar(pasta: Path) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    exe = pasta / ARQUIVO
    exe.write_bytes(b"")
    exe.chmod(0o755)
    return exe


@pytest.fixture
def maquina(tmp_path, monkeypatch):
    """Uma máquina sem a variável, com PATH vazio e sem pasta conhecida."""
    vazia = tmp_path / "path_vazio"
    vazia.mkdir()
    monkeypatch.chdir(vazia)
    monkeypatch.delenv("CG_PG_BIN", raising=False)
    monkeypatch.setenv("PATH", str(vazia))
    monkeypatch.setattr(banco_pg, "_PASTAS_DO_POSTGRES", ())
    return tmp_path


def _moldes(monkeypatch, *moldes):
    monkeypatch.setattr(banco_pg, "_PASTAS_DO_POSTGRES", tuple(str(m) for m in moldes))


def test_sem_variavel_e_sem_path_acha_na_pasta_de_instalacao(maquina, monkeypatch):
    exe = _instalar(maquina / "casa" / "pg18" / "pgsql" / "bin")
    _moldes(monkeypatch, maquina / "casa" / "pg*" / "pgsql" / "bin")
    assert banco_pg.binario_do_postgres("pg_dump") == exe


def test_a_lista_de_fabrica_tem_a_pasta_da_casa():
    assert r"C:\CartorioGestaoPG\pg*\pgsql\bin" == banco_pg._PASTAS_DO_POSTGRES[0]


def test_a_versao_mais_nova_vence_e_a_conta_e_de_numero(maquina, monkeypatch):
    _instalar(maquina / "pg9" / "bin")
    exe = _instalar(maquina / "pg18" / "bin")
    _moldes(monkeypatch, maquina / "pg*" / "bin")
    assert banco_pg.binario_do_postgres("pg_dump") == exe


def test_pasta_sem_o_binario_nao_para_a_procura(maquina, monkeypatch):
    (maquina / "pg18" / "bin").mkdir(parents=True)
    exe = _instalar(maquina / "pg17" / "bin")
    _moldes(monkeypatch, maquina / "pg*" / "bin")
    assert banco_pg.binario_do_postgres("pg_dump") == exe


def test_a_pasta_da_casa_vem_antes_da_do_instalador(maquina, monkeypatch):
    casa = _instalar(maquina / "casa" / "pg17" / "bin")
    _instalar(maquina / "instalador" / "18" / "bin")
    _moldes(monkeypatch, maquina / "casa" / "pg*" / "bin", maquina / "instalador" / "*" / "bin")
    assert banco_pg.binario_do_postgres("pg_dump") == casa


def test_a_variavel_vence_o_path_e_a_pasta_conhecida(maquina, monkeypatch):
    indicado = _instalar(maquina / "indicado")
    _instalar(maquina / "no_path")
    _instalar(maquina / "pg18" / "bin")
    monkeypatch.setenv("CG_PG_BIN", str(maquina / "indicado"))
    monkeypatch.setenv("PATH", str(maquina / "no_path"))
    _moldes(monkeypatch, maquina / "pg*" / "bin")
    assert banco_pg.binario_do_postgres("pg_dump") == indicado


def test_o_path_vence_a_pasta_conhecida(maquina, monkeypatch):
    no_path = _instalar(maquina / "no_path")
    _instalar(maquina / "pg18" / "bin")
    monkeypatch.setenv("PATH", str(maquina / "no_path"))
    _moldes(monkeypatch, maquina / "pg*" / "bin")
    assert Path(banco_pg.binario_do_postgres("pg_dump")).parent == no_path.parent


def test_variavel_com_pasta_errada_ainda_acha_o_binario(maquina, monkeypatch):
    exe = _instalar(maquina / "pg18" / "bin")
    monkeypatch.setenv("CG_PG_BIN", str(maquina / "nao_existe"))
    _moldes(monkeypatch, maquina / "pg*" / "bin")
    assert banco_pg.binario_do_postgres("pg_dump") == exe


def test_sem_binario_em_lugar_nenhum_a_frase_diz_o_que_fazer(maquina):
    with pytest.raises(banco_pg.OperationalError, match=r"pg_dump não encontrado.*CG_PG_BIN"):
        banco_pg.binario_do_postgres("pg_dump")
