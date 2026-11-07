"""`tools/reserva.py` — as partes que não precisam de dois bancos. O caminho inteiro (montar, a
versão nova, assumir) foi ensaiado com dois PostgreSQL 18 em 07/11/2026; o roteiro está em
`docs/SERVIDOR_RESERVA_MACOS.md`."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import reserva as R  # noqa: E402


def test_o_sql_do_principal_e_idempotente_e_tem_as_travas():
    sql = R.sql_do_principal("producao", "cg")
    assert "wal_level = 'logical'" in sql
    assert f"max_slot_wal_keep_size = '{R.TETO_DO_LOG}'" in sql   # o disco do principal
    assert "pg_reload_conf()" in sql                              # o teto vale sem reiniciar
    assert "REPLICA IDENTITY FULL" in sql                          # tabela sem chave
    assert "WHERE NOT EXISTS (SELECT 1 FROM pg_publication" in sql
    assert "PASSWORD :'senha'" in sql and "senha=" not in sql.split("\n", 3)[3]
    assert "SUPERUSER" not in sql.upper()


@pytest.mark.parametrize("schema, dono", [("producao; drop", "cg"), ("producao", "cg x")])
def test_nome_estranho_e_recusado(schema, dono):
    with pytest.raises(ValueError):
        R.sql_do_principal(schema, dono)


def test_a_diferenca_de_esquema_so_ve_o_que_falta():
    principal = {"a": {"id": "bigint", "nova": "text"}, "b": {"id": "bigint"}}
    reserva = {"a": {"id": "bigint", "velha": "text"}}
    faltam, colunas = R.diferenca_de_esquema(principal, reserva)
    assert faltam == ["b"]
    assert colunas == [("a", "nova", "text")]


def test_senha_na_conexao_e_recusada(monkeypatch):
    monkeypatch.setenv("CG_RESERVA_LOCAL_DSN", "host=x user=cg password=segredo")
    with pytest.raises(SystemExit, match="pgpass"):
        R.main(["situacao"])


def test_assumir_sem_a_frase_nao_faz_nada(monkeypatch, capsys):
    monkeypatch.setenv("CG_RESERVA_LOCAL_DSN", "host=127.0.0.1 port=1 user=cg dbname=nada")
    assert R.main(["assumir"]) == 2          # nem conecta
    assert "DESLIGADO" in capsys.readouterr().out
