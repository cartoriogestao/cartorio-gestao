"""A escolha de onde transcrever, com o sistema de pé.

O QUE ELES DEFENDEM
    Que a casa nasce na OpenAI, e que nada liga este servidor por fora da conferência: nem o
    formulário montado à mão. Quem atende vê a tela; quem grava é o ADMIN.
"""
from __future__ import annotations

import re

import pytest

import wa_atendente as ATENDENTE
import wa_schema as SCH
import wa_transcricao_local as LOCAL


@pytest.fixture(scope="module")
def app(cg_app):
    return cg_app


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str, papel: str):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", papel)
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _config(app) -> dict:
    with app.extensions["db"].connect() as con:
        return ATENDENTE.configuracao(con)


def _postar(c, caminho: str, **dados):
    tok = _token(c.get("/whatsapp/atendente").get_data(as_text=True))
    return c.post(caminho, data={**dados, "csrf_token": tok})


def test_a_casa_nasce_na_openai(app):
    assert _config(app)["audio_onde"] == LOCAL.OPENAI


def _tela(app, monkeypatch, usuario: str, *, programa: bool, modelo: bool) -> str:
    monkeypatch.setattr(LOCAL, "programa_instalado", lambda: programa)
    monkeypatch.setattr(LOCAL, "modelo_baixado", lambda pasta: modelo)
    return _entrar(app, usuario, "ADMIN").get("/whatsapp/atendente").get_data(as_text=True)


def test_a_tela_mostra_a_escolha_e_o_que_falta(app, monkeypatch):
    html = _tela(app, monkeypatch, "wa_local_a", programa=False, modelo=False)
    assert 'id="transcricao"' in html
    assert 'value="AQUI"' in html
    assert "não instalado" in html
    assert "/whatsapp/transcricao/baixar" not in html
    assert "/whatsapp/transcricao/conferir" not in html


def test_com_o_programa_a_tela_oferece_o_download(app, monkeypatch):
    html = _tela(app, monkeypatch, "wa_local_g", programa=True, modelo=False)
    assert "/whatsapp/transcricao/baixar" in html
    assert "/whatsapp/transcricao/conferir" not in html


def test_com_o_programa_e_o_modelo_a_tela_oferece_a_conferencia(app, monkeypatch):
    html = _tela(app, monkeypatch, "wa_local_h", programa=True, modelo=True)
    assert "/whatsapp/transcricao/conferir" in html
    assert "/whatsapp/transcricao/baixar" not in html


def test_sem_conferencia_nao_liga_nem_com_o_formulario_na_mao(app):
    c = _entrar(app, "wa_local_b", "ADMIN")
    assert _postar(c, "/whatsapp/transcricao/onde", onde=LOCAL.AQUI).status_code == 302
    assert _config(app)["audio_onde"] == LOCAL.OPENAI


def test_escolha_desconhecida_nao_grava(app):
    c = _entrar(app, "wa_local_c", "ADMIN")
    _postar(c, "/whatsapp/transcricao/onde", onde="QUALQUER")
    assert _config(app)["audio_onde"] == LOCAL.OPENAI


@pytest.mark.parametrize("caminho", ["/whatsapp/transcricao/onde", "/whatsapp/transcricao/baixar",
                                     "/whatsapp/transcricao/conferir"])
def test_so_o_admin_grava(app, caminho):
    c = _entrar(app, "wa_local_d", "USER")
    assert _postar(c, caminho, onde=LOCAL.OPENAI).status_code == 403


def test_com_a_conferencia_aprovada_liga_e_volta(app, monkeypatch):
    c = _entrar(app, "wa_local_e", "ADMIN")
    monkeypatch.setattr(LOCAL, "programa_instalado", lambda: True)
    monkeypatch.setattr(LOCAL, "modelo_baixado", lambda pasta: True)
    d = app.extensions["db"]
    with d.transaction() as con:
        ATENDENTE.guardar_conferencia(con, {"ok": True, "quando": "2026-12-20", "por": "Mario"})
    _postar(c, "/whatsapp/transcricao/onde", onde=LOCAL.AQUI)
    assert _config(app)["audio_onde"] == LOCAL.AQUI
    _postar(c, "/whatsapp/transcricao/onde", onde=LOCAL.OPENAI)
    assert _config(app)["audio_onde"] == LOCAL.OPENAI
    with d.transaction() as con:
        ATENDENTE.guardar_conferencia(con, {})


def test_a_conferencia_pela_tela_nao_guarda_o_texto(app, monkeypatch):
    c = _entrar(app, "wa_local_f", "ADMIN")
    monkeypatch.setattr(LOCAL, "conferir", lambda *a, **k: {
        "ok": True, "motivo": "", "texto": "meu CPF é tal", "quando": "2026-12-20", "por": "Mario",
        "modelo": LOCAL.MODELO, "memoria_livre_mb": 12000, "segundos": 4.0, "trabalho_s": 20.0})
    from io import BytesIO
    tok = _token(c.get("/whatsapp/atendente").get_data(as_text=True))
    r = c.post("/whatsapp/transcricao/conferir", content_type="multipart/form-data",
               data={"csrf_token": tok, "audio": (BytesIO(b"audio"), "teste.ogg", "audio/ogg")})
    assert r.status_code == 302
    d = app.extensions["db"]
    with d.connect() as con:
        cfg = ATENDENTE.configuracao(con)
        guardado = ATENDENTE._ler(con, SCH.CHAVE_AUDIO_CONFERENCIA)
    assert cfg["audio_conferencia"]["ok"] is True
    assert "CPF" not in guardado
    with d.transaction() as con:
        ATENDENTE.guardar_conferencia(con, {})
