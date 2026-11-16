"""Troca autenticada do certificado publico, sem ler ou alterar o segredo."""
from contextlib import nullcontext
from functools import wraps
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask, abort, jsonify, session
import onr_certidoes_web as WEB

@pytest.fixture
def casa(monkeypatch, tmp_path):
    app = Flask(__name__)
    app.secret_key = "somente-teste"
    gravados, auditoria = [], []
    estado = {"cpf": "00000000000", "certificado": "ANTIGO", "tem_chave": True}
    certificados = [{"SERIALNUMBER": "NOVO", "SUBJECTCN": "USUARIO DE TESTE"}]
    monkeypatch.setattr(WEB.OC, "init_schema", lambda con: None)
    monkeypatch.setattr(WEB.WS, "situacao", lambda *args, **kwargs: dict(estado))
    def listar(cpf):
        assert cpf == estado["cpf"]
        return list(certificados)
    monkeypatch.setattr(WEB.WS, "certificados_do_windows", listar)
    monkeypatch.setattr(WEB.WS, "configurar", lambda **kw: gravados.append(kw))
    monkeypatch.setattr(WEB, "render_template", lambda nome, **kw: jsonify(template=nome, **kw))
    def roles_required(*roles):
        def decorate(fn):
            @wraps(fn)
            def guarded(*args, **kwargs):
                if session.get("role") not in roles:
                    abort(403)
                return fn(*args, **kwargs)
            return guarded
        return decorate
    app.extensions.update(usuario_nome=lambda: "ADMIN DE TESTE", usuario_id=lambda: 1,
                          archive_root=lambda: tmp_path)
    db = SimpleNamespace(db_path=tmp_path / "teste.sqlite3", now=lambda: "2026-01-01",
                         connect=lambda: nullcontext(None), get_setting=lambda key, default: default)
    WEB.registrar_rotas(app, db, lambda fn: fn, roles_required, lambda *args: auditoria.append(args))
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["role"] = "ADMIN"
    return SimpleNamespace(client=client, gravados=gravados, auditoria=auditoria,
                           estado=estado, certificados=certificados, pasta=tmp_path)

URL = "/ri/onr/certidoes/certificado"

@pytest.mark.parametrize("role", [None, "USER", "MANAGER"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_somente_administrador_troca_o_certificado(casa, role, method):
    with casa.client.session_transaction() as sess:
        sess["role"] = role
    assert getattr(casa.client, method)(URL).status_code == 403
    assert not casa.gravados


def test_grava_somente_a_serie_valida_e_audita_sem_segredos(casa):
    response = casa.client.post(URL, data={"certificado": " novo "})
    assert response.status_code == 302
    assert casa.gravados == [{"ambiente": WEB.WS.PRODUCAO, "pasta": casa.pasta,
                              "certificado": "NOVO"}]
    assert casa.auditoria == [("ONR_CERTIFICADO_ALTERADO", "WSOFICIO", None,
                              {"ambiente": WEB.WS.PRODUCAO, "serie_anterior": "ANTIGO", "serie": "NOVO"})]

@pytest.mark.parametrize("serie", ["", "ANTIGO", "OUTRO-CPF"])
def test_serie_ausente_antiga_ou_de_outro_cpf_nao_e_gravada(casa, serie):
    assert casa.client.post(URL, data={"certificado": serie}).status_code == 302
    assert not casa.gravados
    assert not casa.auditoria


def test_sem_cpf_nao_enumera_certificados_nem_grava(casa):
    casa.estado["cpf"] = ""
    assert casa.client.get(URL).json["certificados"] == []
    casa.client.post(URL, data={"certificado": "NOVO"})
    assert not casa.gravados


def test_falha_do_windows_fica_legivel_e_nao_grava(casa, monkeypatch):
    def falha(cpf):
        raise WEB.WS.WSOficioError("Windows indisponivel")
    monkeypatch.setattr(WEB.WS, "certificados_do_windows", falha)
    assert casa.client.get(URL).json["erro"] == "Windows indisponivel"
    casa.client.post(URL, data={"certificado": "NOVO"})
    assert not casa.gravados
