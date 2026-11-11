"""O botão de emergência, a volta e a trava que impediu o pytest de 11/11/2026.

Nada aqui abre o PostgreSQL da casa. Onde o comando de verdade conectaria,
o teste troca a abertura por uma falha: se a trava não segurar, o teste quebra
antes de chegar na porta 5434.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "tools"))
sys.path.insert(0, str(RAIZ))

import contingencia as C  # noqa: E402
import reserva as R  # noqa: E402
import trava_producao as T  # noqa: E402

LOCAL_DA_CASA = "host=127.0.0.1 port=5434 user=cg dbname=cartorio"
PRINCIPAL = "host=10.0.0.1 port=5434 user=cg_replica dbname=cartorio"


def test_a_suite_recusa_o_schema_producao():
    with pytest.raises(T.ProducaoProtegida, match="producao"):
        T.exigir_schema_de_teste("producao")
    with pytest.raises(T.ProducaoProtegida):
        T.exigir_schema_de_teste("ensaio_final")
    T.exigir_schema_de_teste("")
    T.exigir_schema_de_teste("cg_abc123")


def test_o_conftest_morre_antes_de_conectar():
    env = os.environ.copy()
    env["CG_TEST_BACKEND"] = "pg"
    env["CG_PG_SCHEMA"] = "producao"
    env["CG_PG_DSN"] = "host=127.0.0.1 port=1 user=u dbname=x"
    env.pop("CG_MODO_RESERVA", None)
    feito = subprocess.run(
        [sys.executable, "-c", "import tests.conftest"],
        cwd=RAIZ, env=env, capture_output=True, text=True, check=False)
    assert feito.returncode != 0
    assert "producao" in (feito.stderr + feito.stdout).lower()


def test_destruir_producao_e_recusado():
    with pytest.raises(T.ProducaoProtegida):
        T.exigir_schema_descartavel("producao", origem="teste")
    with pytest.raises(T.ProducaoProtegida):
        T.exigir_schema_descartavel("public", origem="teste")


def test_montar_recusa_a_porta_da_producao(monkeypatch):
    monkeypatch.delenv("CG_MODO_RESERVA", raising=False)
    with pytest.raises(T.ProducaoProtegida):
        T.recusar_montar(LOCAL_DA_CASA, PRINCIPAL, "producao")
    with pytest.raises(T.ProducaoProtegida):
        T.recusar_montar(LOCAL_DA_CASA, LOCAL_DA_CASA, "cg_ensaio")


def test_montar_na_reserva_do_mac_segue(monkeypatch):
    monkeypatch.setenv("CG_MODO_RESERVA", "1")
    T.recusar_montar(LOCAL_DA_CASA, PRINCIPAL, "producao")


def test_montar_nao_abre_conexao(monkeypatch):
    monkeypatch.delenv("CG_MODO_RESERVA", raising=False)
    monkeypatch.setenv("CG_RESERVA_LOCAL_DSN", LOCAL_DA_CASA)
    monkeypatch.setenv("CG_RESERVA_PRINCIPAL_DSN", PRINCIPAL)

    def conectou(*_a, **_k):
        raise AssertionError("abriu conexão")

    monkeypatch.setattr(R, "_abrir", conectou)
    assert R.main(["montar"]) == 2


def test_migrar_recriar_recusa_antes_de_conectar(tmp_path, capsys):
    sys.path.insert(0, str(RAIZ / "tools"))
    import migrar_para_postgres as M
    banco = tmp_path / "vazio.sqlite3"
    sqlite3.connect(banco).close()
    codigo = M.principal([
        "--sqlite", str(banco),
        "--dsn", "host=127.0.0.1 port=1 user=u dbname=x",
        "--schema", "producao", "--recriar"])
    assert codigo == 2
    assert "Recuso" in capsys.readouterr().err


def test_emergencia_trava_antes_de_promover():
    passos = []

    def anotar(nome):
        def _fazer():
            passos.append(nome)
        return _fazer

    assert R.executar_emergencia(
        confirmacao="EMERGENCIA", principal_alcancavel=True, tem_assinatura=True,
        travar_principal=anotar("somente_leitura"), desligar=anotar("desligar"),
        despejar=anotar("despejo"), promover=anotar("promover")) == 0
    assert passos == ["somente_leitura", "desligar", "despejo", "promover"]


def test_emergencia_sem_frase_nao_faz_nada():
    def boom():
        raise AssertionError("não devia rodar")

    assert R.executar_emergencia(
        confirmacao="", principal_alcancavel=True, tem_assinatura=True,
        travar_principal=boom, desligar=boom, despejar=boom, promover=boom) == 2


def test_emergencia_segue_se_o_principal_nao_responde():
    passos = []
    assert R.executar_emergencia(
        confirmacao="ASSUMIR", principal_alcancavel=False, tem_assinatura=True,
        travar_principal=lambda: passos.append("trava"),
        desligar=lambda: passos.append("desligar"),
        despejar=lambda: passos.append("despejo"),
        promover=lambda: passos.append("promover")) == 0
    assert passos == ["desligar", "despejo", "promover"]


def test_a_volta_so_solta_quando_a_conferencia_fecha():
    antes = {"atos": R.Retrato(2, 2, "aa")}
    depois = {"atos": R.Retrato(2, 2, "aa")}
    soltou = []
    assert R.executar_volta(
        confirmacao="VOLTAR", principal={"atos": R.Retrato(1, 1, "a")}, reserva=antes,
        copiar=lambda tabelas: None, reler=lambda: (depois, depois),
        acertar=lambda: soltou.append("sequencias"),
        remontar=lambda: soltou.append("remontar"),
        soltar=lambda: soltou.append("soltar"), remonta=True) == 0
    assert soltou == ["sequencias", "remontar", "soltar"]


def test_a_volta_parada_nao_religa_nem_solta():
    divergente = {"atos": R.Retrato(2, 2, "diferente")}
    feito = []
    assert R.executar_volta(
        confirmacao="VOLTAR", principal=divergente, reserva=divergente,
        copiar=lambda _t: feito.append("copiar"),
        reler=lambda: ({"atos": R.Retrato(1, 1, "a")}, divergente),
        acertar=lambda: feito.append("sequencias"),
        remontar=lambda: feito.append("remontar"),
        soltar=lambda: feito.append("soltar"), remonta=True) == 1
    assert feito == ["copiar"]


def test_remontar_nao_leva_senha_e_nao_copia_de_novo():
    with pytest.raises(ValueError):
        R.comandos_de_remontar("host=10.0.0.1 port=5434 user=cg password=segredo dbname=cartorio")
    comandos = R.comandos_de_remontar("host=10.0.0.1 port=5434 user=cg_replica dbname=cartorio")
    texto = "\n".join(comandos)
    assert "DROP SUBSCRIPTION IF EXISTS cg_reserva" in texto
    assert "copy_data = false" in texto
    assert "password" not in texto
    assert "CREATE SUBSCRIPTION cg_reserva" in texto


def test_o_despejo_nao_leva_senha(tmp_path):
    with pytest.raises(T.ProducaoProtegida):
        R.comando_de_despejo("pg_dump", "host=x password=segredo", "cg_ensaio", tmp_path / "a.dump")
    argv = R.comando_de_despejo(
        "pg_dump", "host=127.0.0.1 port=5435 user=cg dbname=ensaio", "cg_ensaio", tmp_path / "a.dump")
    assert not any("password=" in parte.lower() for parte in argv)
    assert "--no-password" in argv


def test_somente_leitura_pelo_ambiente(monkeypatch, tmp_path):
    C.esquecer()
    monkeypatch.delenv("CG_SOMENTE_LEITURA", raising=False)
    monkeypatch.setenv("CARTORIO_GESTAO_DATA", str(tmp_path))
    assert C.ativo() is False
    monkeypatch.setenv("CG_SOMENTE_LEITURA", "1")
    assert C.ativo() is True
    monkeypatch.delenv("CG_SOMENTE_LEITURA")
    C.esquecer()
    (tmp_path / "somente_leitura").write_text("1", encoding="ascii")
    assert C.ativo() is True


def test_o_tique_nao_lanca_em_somente_leitura(monkeypatch):
    monkeypatch.setenv("CG_SOMENTE_LEITURA", "1")
    import automacao

    class Banco:
        def transaction(self):
            raise AssertionError("a automação não abre transação")

    resumo = automacao.tique(Banco())
    assert resumo["lancadas"] == []
    assert resumo["puladas"] == ["somente_leitura"]


def test_o_ensaio_nao_abre_banco():
    from tools.ensaio_contingencia import ensaio
    assert ensaio() == 0


def test_a_faixa_e_a_recusa_de_formulario():
    from jinja2 import Environment, FileSystemLoader
    html = Environment(loader=FileSystemLoader(RAIZ / "templates")).get_template(
        "_faixa_reserva.html").render(
            MODO_RESERVA=False, CONTINGENCIA=True, AVISO_CONTINGENCIA=C.AVISO,
            AVISO_RESERVA="")
    assert "SOMENTE LEITURA" in html
    assert C.bloqueia_escrita("POST", "preferencias_layout") is True
    assert C.bloqueia_escrita("POST", "login") is False
    assert C.bloqueia_escrita("GET", "dashboard") is False
