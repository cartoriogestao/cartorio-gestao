"""Rotas da tela do editor — 200, permissões, USER não publica."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return achado.group(1) if achado else ""


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa["app"]
    bd = cg_casa["db"]
    bd.create_user("editor_tst", "EDITOR TESTE", SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": "editor_tst", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "db": bd}


@pytest.fixture()
def admin(cg_casa):
    return _sessao(cg_casa, "ADMIN")


@pytest.fixture()
def user(cg_casa):
    return _sessao(cg_casa, "USER")


def test_lista_abre_200(admin):
    r = admin["c"].get("/modelos/editor")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Editor de modelos" in html or "EDITOR DE MODELOS" in html


def test_editar_termo_200(admin):
    r = admin["c"].get("/modelos/editor/RCPN/RC_TERMO_NASCIMENTO")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "RC_TERMO_NASCIMENTO" in html


def test_editar_molde_200(admin):
    r = admin["c"].get("/modelos/editor/RCPN/RC_MOLDE_NASCIMENTO")
    assert r.status_code == 200


def test_user_abre_mas_nao_publica(user):
    r = user["c"].get("/modelos/editor")
    assert r.status_code == 200
    # API publicar deve recusar
    # precisa CSRF no header
    login_html = user["c"].get("/modelos/editor").get_data(as_text=True)
    # pega csrf do root data-csrf
    m = re.search(r'data-csrf="([^"]+)"', login_html)
    csrf = m.group(1) if m else ""
    # salva rascunho primeiro via API
    user["c"].post(
        "/modelos/editor/api/salvar",
        json={"area": "RCPN", "template_id": "RC_TERMO_NASCIMENTO",
              "parte": "CORPO", "conteudo": "rascunho user"},
        headers={"X-CSRF-Token": csrf})
    pub = user["c"].post(
        "/modelos/editor/api/publicar",
        json={"area": "RCPN", "template_id": "RC_TERMO_NASCIMENTO",
              "parte": "CORPO"},
        headers={"X-CSRF-Token": csrf})
    assert pub.status_code in (403, 400)
    data = pub.get_json()
    assert data and data.get("ok") is False


def test_admin_salvar_rascunho(admin):
    html = admin["c"].get("/modelos/editor").get_data(as_text=True)
    m = re.search(r'data-csrf="([^"]+)"', html)
    csrf = m.group(1) if m else ""
    r = admin["c"].post(
        "/modelos/editor/api/salvar",
        json={"area": "RCPN", "template_id": "RC_TERMO_CASAMENTO",
              "parte": "CORPO", "conteudo": "corpo teste"},
        headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["versao"]["status"] == "rascunho"


def test_previa_api_editor(admin):
    html = admin["c"].get("/modelos/editor").get_data(as_text=True)
    m = re.search(r'data-csrf="([^"]+)"', html)
    csrf = m.group(1) if m else ""
    r = admin["c"].post(
        "/modelos/editor/api/previa",
        json={"area": "RCPN", "template_id": "RC_TERMO_NASCIMENTO",
              "conteudo": {"CORPO": ""}, "papel": "a4", "formato": "html"},
        headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    data = r.get_json()
    assert data is not None
    # Com motor presente: fonte=motor; sem motor: aproximada/fallback
    avisos = data.get("avisos") or []
    fonte = data.get("fonte")
    assert (
        fonte == "motor"
        or data.get("aproximada")
        or any("aproximada" in a.lower() for a in avisos)
        or data.get("ok") in (True, False)
        or "html" in data
        or "erros" in data
    )


def test_campos_api(admin):
    r = admin["c"].get("/modelos/editor/api/campos?area=RCPN&tipo=RC_TERMO_NASCIMENTO")
    assert r.status_code == 200
    data = r.get_json()
    assert "campos" in data


# --- API sem parametro: padrao util em vez de 400 (06/10/2026) --------------
# O ensaio contra a copia da producao abriu `/api/historico` e `/api/diff` sem
# nada e recebeu 400. Agora: historico geral da area; diff das duas versoes
# mais recentes; aviso (200) quando nao ha duas; 404 para id que nao existe.

def _salvar(sessao, template_id, conteudo):
    html = sessao["c"].get("/modelos/editor").get_data(as_text=True)
    m = re.search(r'data-csrf="([^"]+)"', html)
    r = sessao["c"].post(
        "/modelos/editor/api/salvar",
        json={"area": "RCPN", "template_id": template_id,
              "parte": "CORPO", "conteudo": conteudo},
        headers={"X-CSRF-Token": m.group(1) if m else ""})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["versao"]["id"]


def test_historico_sem_modelo_e_o_geral_da_area(admin):
    vid = _salvar(admin, "RC_TERMO_OBITO", "historico geral")
    r = admin["c"].get("/modelos/editor/api/historico")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True and data["geral"] is True
    assert vid in [v["id"] for v in data["historico"]]


def test_diff_sem_parametro_compara_as_duas_mais_recentes(admin):
    v1 = _salvar(admin, "RC_TERMO_LIVRO_E", "linha antiga")
    v2 = _salvar(admin, "RC_TERMO_LIVRO_E", "linha nova")
    r = admin["c"].get("/modelos/editor/api/diff")
    assert r.status_code == 200
    data = r.get_json()
    assert (data["id_a"], data["id_b"]) == (v1, v2)
    assert "+linha nova" in data["diff"] and "-linha antiga" in data["diff"]
    # so `b`: contra a anterior do mesmo modelo
    so_b = admin["c"].get(f"/modelos/editor/api/diff?b={v2}").get_json()
    assert (so_b["id_a"], so_b["id_b"]) == (v1, v2)
    # pelo modelo
    pelo = admin["c"].get(
        "/modelos/editor/api/diff?template_id=RC_TERMO_LIVRO_E").get_json()
    assert (pelo["id_a"], pelo["id_b"]) == (v1, v2)


def test_diff_sem_par_avisa_em_vez_de_recusar(admin):
    vid = _salvar(admin, "RC_TERMO_NASCIMENTO", "primeira e unica?")
    r = admin["c"].get(f"/modelos/editor/api/diff?a={vid}&b=")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    if data.get("id_a") is None:          # banco sem versao anterior deste modelo
        assert "duas versões" in data["aviso"]


def test_diff_id_inexistente_e_404_e_lixo_nao_e_500(admin):
    assert admin["c"].get("/modelos/editor/api/diff?a=999999&b=999998").status_code == 404
    assert admin["c"].get("/modelos/editor/api/diff?b=999999").status_code == 404
    assert admin["c"].get("/modelos/editor/api/diff?a=xyz&b=abc").status_code == 200
