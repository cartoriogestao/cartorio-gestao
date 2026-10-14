# -*- coding: utf-8 -*-
"""Migracao B0: settings da serventia — backup antes, idempotente, nunca sobrescreve.

Tudo com banco e perfil SINTETICOS em tmp_path (valores ficticios).
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3

import pytest

from tools import migrar_settings_serventia_b0 as MIG

PERFIL_FICTICIO = {
    "unit_name": "SERVENTIA FICTICIA DE TESTE",
    "serventia_titular": "Titular Ficticio",
    "ri_cns": "000000",
    "serventia_cnpj": "00.000.001/0000-55",
    "ri_cidade": "Cidade Ficticia",
    "ri_uf": "ZZ",
    "serventia_brasao": "static/brasao.jpg",
    "selador_host": "127.0.0.1",
    "chave_fora_de_campos": "ignorada",
}


def _banco(tmp_path, linhas=None):
    banco = tmp_path / "cartorio_gestao.sqlite3"
    con = sqlite3.connect(banco)
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    for k, v in (linhas or {}).items():
        con.execute("INSERT INTO settings VALUES (?,?)", (k, v))
    con.commit()
    con.close()
    return banco


def _settings(banco):
    con = sqlite3.connect(banco)
    try:
        return dict(con.execute("SELECT key, value FROM settings"))
    finally:
        con.close()


def _perfil(tmp_path):
    caminho = tmp_path / MIG.NOME_DO_PERFIL
    caminho.write_text(json.dumps(PERFIL_FICTICIO), encoding="utf-8")
    return MIG.ler_perfil(caminho)


def test_campos_incluem_as_chaves_novas():
    for k in ("serventia_brasao", "selador_host", "ri_cns", "serventia_cnpj"):
        assert k in MIG.campos()


def test_perfil_filtra_chaves_desconhecidas(tmp_path):
    perfil = _perfil(tmp_path)
    assert "chave_fora_de_campos" not in perfil
    assert perfil["ri_cns"] == "000000"


def test_grava_so_o_vazio_com_backup_e_segunda_vez_e_no_op(tmp_path):
    banco = _banco(tmp_path, {"unit_name": "JA PREENCHIDO", "ri_uf": "  ",
                              "outra_chave": "x"})
    perfil = _perfil(tmp_path)
    r1 = MIG.migrar(banco, perfil, agora=dt.datetime(2026, 10, 5, 15, 0, 0))
    assert r1["backup"] and r1["backup"].is_file()
    assert r1["backup"].parent.name == "backups"
    s = _settings(banco)
    assert s["unit_name"] == "JA PREENCHIDO"          # nao sobrescreve
    assert s["ri_uf"] == "ZZ"                          # branco conta como vazio
    assert s["serventia_titular"] == "Titular Ficticio"
    assert s["outra_chave"] == "x"
    assert "unit_name" not in r1["gravadas"]
    # o backup e o banco ANTES da escrita
    assert _settings(r1["backup"]).get("serventia_titular") is None

    r2 = MIG.migrar(banco, perfil, agora=dt.datetime(2026, 10, 5, 15, 0, 1))
    assert r2["gravadas"] == {} and r2["backup"] is None
    assert _settings(banco) == s
    assert len(list((tmp_path / "backups").iterdir())) == 1


def test_simular_nao_grava_nem_faz_backup(tmp_path):
    banco = _banco(tmp_path)
    r = MIG.migrar(banco, _perfil(tmp_path), simular=True)
    assert r["pendentes"] and not r["gravadas"] and r["backup"] is None
    assert _settings(banco) == {}
    assert not (tmp_path / "backups").exists()


def test_recusa_banco_da_producao(tmp_path, monkeypatch):
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    prod = tmp_path / "CartorioGestao"
    prod.mkdir()
    banco = _banco(prod)
    with pytest.raises(MIG.MigracaoRecusou):
        MIG.conferir_alvo(banco, sou_a_producao=False)
    MIG.conferir_alvo(banco, sou_a_producao=True)   # so com a flag explicita


def test_localiza_pelo_cartorio_gestao_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CARTORIO_GESTAO_DATA", str(tmp_path))
    banco, origem = MIG.localizar_banco()
    assert banco == (tmp_path / MIG.NOME_DO_BANCO).resolve()
    assert origem == "CARTORIO_GESTAO_DATA"


def test_gravar_perfil_nunca_sobrescreve(tmp_path):
    alvo = tmp_path / MIG.NOME_DO_PERFIL
    assert MIG.gravar_perfil(alvo, {"ri_cns": "000000"}) is True
    assert MIG.gravar_perfil(alvo, {"ri_cns": "999999"}) is False
    assert json.loads(alvo.read_text(encoding="utf-8")) == {"ri_cns": "000000"}


def test_gerar_perfil_recusa_quando_padrao_ja_e_generico(monkeypatch):
    import serventia
    monkeypatch.setattr(serventia, "PADRAO", dict(serventia.PADRAO_GENERICO))
    with pytest.raises(MIG.MigracaoRecusou):
        MIG.perfil_do_codigo_antigo()


def test_main_sem_perfil_recusa_com_codigo_2(tmp_path, capsys):
    banco = _banco(tmp_path)
    assert MIG.main(["--banco", str(banco)]) == 2
    assert "Perfil local nao encontrado" in capsys.readouterr().out


def test_selador_config_le_o_host_de_settings():
    import selador_config as SC
    assert SC.base_sugerida({}) is None
    assert SC.base_sugerida({"selador_host": "127.0.0.1"}) == "https://127.0.0.1:443"
    assert SC.base_sugerida(lambda: {"selador_host": "https://h.exemplo:9443/"}) == "https://h.exemplo:9443"
