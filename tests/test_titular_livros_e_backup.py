"""LIVRO-CAIXA E BACKUP APARECEM SÓ PARA O TITULAR.

Ordem do oficial (01/11/2026): «livro caixa e backup devem aparecer apenas para mim». Ser ADMIN
não basta. Vale na rota, no menu e na tela, e quem não é o titular também não muda a pasta dos
backups nem o nome do titular pelas configurações.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from tests.conftest import cg_login

SENHA = "Senha#12345"
TITULAR = "MARIO EXEMPLO DOS SANTOS"
DIARIO = "/livros-obrigatorios/diario"
FECHADAS = (DIARIO, "/administrativo/carne-leao", "/administrativo/despesas/configuracao")


def _token(c, url="/configuracoes"):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', c.get(url).get_data(as_text=True)).group(1)


@pytest.fixture
def analista(cg_casa_logada):
    casa = cg_casa_logada
    casa["db"].set_settings({"serventia_titular": TITULAR, "backup_dir": "pasta-do-titular"})
    casa["db"].create_user("analista", "ANALISTA EXEMPLO", SENHA, "ADMIN")
    c = casa["app"].test_client()
    cg_login(c, "analista", SENHA)
    return c


@pytest.mark.parametrize("url", FECHADAS)
def test_outro_admin_nao_abre_e_o_titular_abre(cg_casa_logada, analista, url):
    assert analista.get(url).status_code == 403
    assert cg_casa_logada["c"].get(url).status_code == 200


def test_outro_admin_nao_gera_nem_protege_o_backup(analista):
    token = _token(analista)
    assert analista.post("/backup", data={"csrf_token": token}).status_code == 403
    assert analista.post("/configuracoes/backup-protecao", data={"csrf_token": token}).status_code == 403


def test_as_configuracoes_nao_mostram_o_backup_a_outro_admin(cg_casa_logada, analista):
    tela = analista.get("/configuracoes").get_data(as_text=True)
    for trecho in ('name="backup_dir"', 'name="auto_backup"', 'name="backup_retencao_dias"',
                   "cfg-backup-protecao", "url_for('backup')", 'action="/backup"'):
        assert trecho not in tela, trecho
    do_titular = cg_casa_logada["c"].get("/configuracoes").get_data(as_text=True)
    assert 'name="backup_dir"' in do_titular and 'action="/backup"' in do_titular


def test_o_menu_nao_mostra_o_diario_a_outro_admin(cg_casa_logada, analista):
    assert DIARIO + '"' not in analista.get("/").get_data(as_text=True)
    assert DIARIO + '"' in cg_casa_logada["c"].get("/").get_data(as_text=True)


def test_outro_admin_nao_muda_o_backup_nem_o_titular_pelo_formulario(cg_casa_logada, analista):
    db = cg_casa_logada["db"]
    analista.post("/configuracoes", data={"csrf_token": _token(analista), "unit_name": "Serventia de exemplo",
                                          "serventia_titular": "ANALISTA EXEMPLO", "backup_dir": "pasta-desviada"})
    assert db.get_setting("backup_dir", "") == "pasta-do-titular"
    assert db.get_setting("serventia_titular", "") == TITULAR
    assert db.get_setting("auto_backup", "1") == "1", "o formulário sem o campo não desliga o backup"


def test_a_senha_fecha_o_livro_e_abre_com_a_senha_certa(cg_casa_logada):
    casa, c = cg_casa_logada, cg_casa_logada["c"]
    url = "/administrativo/senha-do-oficial"
    assert c.get(DIARIO).status_code == 200, "sem senha, o login basta"
    c.post(url, data={"csrf_token": _token(c, url), "acao": "gravar", "nova": "senha-do-teste", "confirmacao": "senha-do-teste"})
    assert "senha-do-teste" not in casa["db"].get_setting("titular_senha_hash", "")
    outro = casa["app"].test_client()
    cg_login(outro, "mario", SENHA)
    for fechada in (DIARIO, "/administrativo/carne-leao"):
        assert url in outro.get(fechada).headers["Location"]
    assert "balanço do mês está fechado" in outro.get("/administrativo/despesas").get_data(as_text=True)
    assert "Senha errada" in outro.post(url, data={"csrf_token": _token(outro, url), "acao": "abrir", "senha": "errada-errada"},
                                        follow_redirects=True).get_data(as_text=True)
    assert outro.post(url, data={"csrf_token": _token(outro, url), "acao": "abrir", "senha": "senha-do-teste",
                                 "volta": DIARIO}).headers["Location"].endswith(DIARIO)
    assert outro.get(DIARIO).status_code == 200


def test_tirar_a_senha_pede_a_atual_e_a_volta_nao_sai_da_casa(cg_casa_logada):
    import titular_privado as TP
    casa, c = cg_casa_logada, cg_casa_logada["c"]
    url = "/administrativo/senha-do-oficial"
    c.post(url, data={"csrf_token": _token(c, url), "acao": "gravar", "nova": "senha-do-teste", "confirmacao": "senha-do-teste"})
    c.post(url, data={"csrf_token": _token(c, url), "acao": "remover", "atual": "errada-errada"})
    assert casa["db"].get_setting("titular_senha_hash", "")
    c.post(url, data={"csrf_token": _token(c, url), "acao": "remover", "atual": "senha-do-teste"})
    assert not casa["db"].get_setting("titular_senha_hash", "")
    assert [TP.volta_segura(v) for v in ("//fora.example", "https://fora.example", "/livros")] == ["/", "/", "/livros"]
    # O navegador apaga o TAB do endereço: «/<TAB>/fora» vira «//fora».
    assert TP.volta_segura("/\t/fora.example") == "/" and TP.volta_segura("/\\fora.example") == "/"
