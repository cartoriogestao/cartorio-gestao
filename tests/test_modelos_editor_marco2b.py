"""Marco 2b — arquivo_base64, marcar_bloqueados, fidelidade marcada≡vigente."""
from __future__ import annotations

import base64
import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_editor as ED
import modelos_editor_motor as MOTOR
import modelos_elementos_schema as ESQ
import modelos_moldes as MOLDES
import ri_schema
from modelos_editor_schema import (
    AREA_RCPN, PARTE_CORPO, PARTE_MOLDE, STATUS_PUBLICADA,
    init_modelos_editor_schema,
)

AGORA = "2026-10-05T16:00:00"

TERMOS = (
    "RC_TERMO_NASCIMENTO",
    "RC_TERMO_CASAMENTO",
    "RC_TERMO_OBITO",
    "RC_TERMO_LIVRO_E",
)
MOLDES_IDS = (
    "RC_MOLDE_NASCIMENTO",
    "RC_MOLDE_CASAMENTO",
    "RC_MOLDE_OBITO",
)


@pytest.fixture()
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "t.sqlite3")
    c.row_factory = sqlite3.Row
    ri_schema.init_ri_schema(c)
    ESQ.init_modelos_elementos_schema(c)
    MOLDES.init_modelos_moldes_schema(c)
    init_modelos_editor_schema(c)
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.commit()
    yield c
    c.close()


def _sv():
    return {
        "unit_name": "OFICIO DE EXEMPLO",
        "serventia_titular": "Fulano de Tal",
        "serventia_titulo": "Oficial",
        "ri_substituta": "Beltrana",
        "serventia_cnpj": "00.000.010/0001-27",
        "ri_cns": "000000",
        "serventia_telefone": "(00) 0000-0000",
        "serventia_endereco": "Rua Exemplo, 1",
        "serventia_cep": "00.000-000",
        "ri_cidade": "Cidade Exemplo",
        "ri_uf": "EX",
        "serventia_email": "exemplo@example.com",
        "serventia_brasao": "",
    }


# -------------------- arquivo_base64 (+ alias) --------------------

def test_normalizar_arquivo_base64_prefere_campo_novo():
    r = MOTOR.normalizar_arquivo_resposta({
        "arquivo_base64": "NOVO",
        "pdf_base64": "VELHO",
        "mime": "application/pdf",
    })
    assert r["arquivo_base64"] == "NOVO"
    assert r["pdf_base64"] == "NOVO"


def test_normalizar_arquivo_base64_fallback_pdf_alias():
    r = MOTOR.normalizar_arquivo_resposta({
        "pdf_base64": "SO_ALIAS",
        "mime": "application/pdf",
    })
    assert r["arquivo_base64"] == "SO_ALIAS"
    assert r["pdf_base64"] == "SO_ALIAS"


def test_previa_mock_preenche_arquivo_base64(con):
    fake = base64.b64encode(b"%PDF-1.4 m2b").decode("ascii")

    def fake_mod(payload, *, sv=None, con=None):
        return {
            "arquivo_base64": fake,
            "mime": "application/pdf",
            "avisos": [], "erros": [],
            "fonte": "motor", "aproximada": False,
        }

    with mock.patch.object(MOTOR, "motor_disponivel", return_value=True):
        with mock.patch.object(MOTOR, "previa_via_motor_modulo", side_effect=fake_mod):
            resp = MOTOR.previa(
                con, area="RCPN", template_id="RC_MOLDE_NASCIMENTO",
                formato="pdf", papel="a4")
    assert resp["arquivo_base64"] == fake
    assert resp["pdf_base64"] == fake


def test_previa_mock_alias_pdf_vira_arquivo_base64(con):
    fake = base64.b64encode(b"%PDF-1.4 alias").decode("ascii")

    def fake_mod(payload, *, sv=None, con=None):
        # motor antigo só devolve pdf_base64
        return {
            "pdf_base64": fake,
            "mime": "application/pdf",
            "avisos": [], "erros": [],
            "fonte": "motor", "aproximada": False,
        }

    with mock.patch.object(MOTOR, "motor_disponivel", return_value=True):
        with mock.patch.object(MOTOR, "previa_via_motor_modulo", side_effect=fake_mod):
            resp = MOTOR.previa(
                con, area="RCPN", template_id="RC_TERMO_NASCIMENTO",
                formato="pdf", papel="a4")
    assert resp["arquivo_base64"] == fake
    assert resp["pdf_base64"] == fake


# -------------------- marcar_bloqueados (cliente) --------------------

def test_marcar_bloqueados_mock(monkeypatch):
    def fake_motor():
        class Fake:
            @staticmethod
            def marcar_bloqueados(area, template_id, conteudo):
                return f"MARCADO::{conteudo}"
        return Fake

    monkeypatch.setattr(MOTOR, "motor_disponivel", lambda: True)
    import builtins
    real_import = builtins.__import__

    def _imp(name, *a, **k):
        if name == "modelos_motor":
            return fake_motor()
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _imp)
    # Chama a função real que importa modelos_motor por dentro
    # Nuance: marcar_bloqueados já importa no corpo — patch via sys.modules
    import sys as _sys
    fake = fake_motor()
    monkeypatch.setitem(_sys.modules, "modelos_motor", fake)
    out, avisos = MOTOR.marcar_bloqueados("RCPN", "RC_TERMO_NASCIMENTO", "abc")
    assert out == "MARCADO::abc"
    assert avisos == []


def test_marcar_bloqueados_fallback_motor_ausente(monkeypatch):
    monkeypatch.setattr(MOTOR, "motor_disponivel", lambda: False)
    out, avisos = MOTOR.marcar_bloqueados("RCPN", "RC_TERMO_NASCIMENTO", "intacto")
    assert out == "intacto"
    assert any("ausente" in a.lower() for a in avisos)


def test_marcar_bloqueados_real_termo(con):
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    vig = ED.conteudo_vigente(con, "RC_TERMO_CASAMENTO", PARTE_CORPO)["conteudo"]
    out, avisos = MOTOR.marcar_bloqueados("RCPN", "RC_TERMO_CASAMENTO", vig)
    assert "{{#bloqueado" in out
    assert out != vig
    assert avisos == []
    import modelos_motor as MM
    assert MM.remover_marcadores_bloqueados(out) == vig


# -------------------- exibição (não grava) --------------------

def test_carregar_marcar_so_exibicao_nao_altera_publicada(con):
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    ED.semear_v1(con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
                 autor="t", agora=AGORA)
    pub = ED.carregar(con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
                      parte=PARTE_CORPO, qual="publicada", marcar_para_edicao=False)
    assert "{{#bloqueado" not in (pub.get("conteudo") or "")
    sha = pub["sha256"]
    ed = ED.carregar(con, area=AREA_RCPN, template_id="RC_TERMO_NASCIMENTO",
                     parte=PARTE_CORPO, qual="publicada", marcar_para_edicao=True)
    assert ed.get("marcado_so_exibicao") is True
    assert "{{#bloqueado" in (ed.get("conteudo") or "")
    # DB intacta
    row = con.execute(
        "SELECT conteudo, sha256 FROM mo_versoes WHERE status=? AND template_id=?",
        (STATUS_PUBLICADA, "RC_TERMO_NASCIMENTO")).fetchone()
    assert row["sha256"] == sha
    assert "{{#bloqueado" not in (row["conteudo"] or "")


def test_semear_nao_grava_marcadores(con):
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    ED.semear_v1(con, area=AREA_RCPN, template_id="RC_TERMO_OBITO",
                 autor="t", agora=AGORA)
    row = con.execute(
        "SELECT conteudo FROM mo_versoes WHERE template_id=? AND status=?",
        ("RC_TERMO_OBITO", STATUS_PUBLICADA)).fetchone()
    assert "{{#bloqueado" not in (row["conteudo"] or "")


# -------------------- fidelidade marcada ≡ vigente --------------------

@pytest.mark.parametrize("tpl", TERMOS)
def test_fidelidade_termo_marcado_igual_vigente(con, tpl):
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    import modelos_motor as MM
    vig = ED.conteudo_vigente(con, tpl, PARTE_CORPO)["conteudo"]
    marc = MM.marcar_bloqueados("RCPN", tpl, vig)
    assert marc != vig  # senão o teste não prova nada
    r1 = MM.resposta_previa(area="RCPN", template_id=tpl, formato="html",
                            papel="a4", sv=_sv(), conteudo=vig)
    r2 = MM.resposta_previa(area="RCPN", template_id=tpl, formato="html",
                            papel="a4", sv=_sv(), conteudo=marc)
    h1 = r1.get("html") or r1.get("texto") or ""
    h2 = r2.get("html") or r2.get("texto") or ""
    assert h1 == h2
    assert "{{#bloqueado" not in h1


@pytest.mark.parametrize("tpl", MOLDES_IDS)
def test_fidelidade_molde_marcado_igual_vigente(con, tpl):
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    import modelos_motor as MM
    vig = ED.conteudo_vigente(con, tpl, PARTE_MOLDE)
    cont = vig.get("conteudo")
    if not cont and vig.get("conteudo_blob"):
        cont = base64.b64encode(vig["conteudo_blob"]).decode("ascii")
    marc = MM.marcar_bloqueados("RCPN", tpl, cont)
    # ODT: motor devolve intacto
    assert marc == cont
    r1 = MM.resposta_previa(area="RCPN", template_id=tpl, formato="html",
                            papel="a4", sv=_sv(), conteudo=cont)
    r2 = MM.resposta_previa(area="RCPN", template_id=tpl, formato="html",
                            papel="a4", sv=_sv(), conteudo=marc)
    assert (r1.get("html") or "") == (r2.get("html") or "")


# -------------------- cadeado / adulteração casamento e óbito --------------------

def test_cadeado_ativo_nos_tres_moldes():
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    for tpl in MOLDES_IDS:
        r = MOTOR.trechos_bloqueados(area="RCPN", tipo=tpl)
        assert r["fonte"] == "motor"
        assert len(r.get("trechos") or []) >= 6, tpl


def test_cadeado_ativo_nos_termos():
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    for tpl in TERMOS:
        r = MOTOR.trechos_bloqueados(area="RCPN", tipo=tpl)
        assert r["fonte"] == "motor"
        assert any(t.get("id") for t in (r.get("trechos") or [])), tpl


def test_servidor_recusa_adulterado_casamento(con):
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    r = MOTOR.trechos_bloqueados(area="RCPN", tipo="RC_TERMO_CASAMENTO")
    lit = [t for t in r["trechos"] if t.get("literal")]
    assert lit
    bid = lit[0]["id"]
    corpo = f"x\n{{{{#bloqueado {bid}}}}}TEXTO ADULTERADO{{{{/bloqueado}}}}\ny"
    with pytest.raises(ED.EditorError, match="recusada|alterado|bloqueado"):
        ED.salvar_rascunho(
            con, area=AREA_RCPN, template_id="RC_TERMO_CASAMENTO",
            parte=PARTE_CORPO, conteudo=corpo, autor="t", agora=AGORA,
            get_settings=_sv)


def test_servidor_recusa_adulterado_obito(con):
    if not MOTOR.motor_disponivel():
        pytest.skip("motor ausente")
    r = MOTOR.trechos_bloqueados(area="RCPN", tipo="RC_TERMO_OBITO")
    lit = [t for t in r["trechos"] if t.get("literal")]
    assert lit
    bid = lit[0]["id"]
    corpo = f"{{{{#bloqueado {bid}}}}}HACKEADO{{{{/bloqueado}}}}"
    with pytest.raises(ED.EditorError, match="recusada|alterado|bloqueado"):
        ED.salvar_rascunho(
            con, area=AREA_RCPN, template_id="RC_TERMO_OBITO",
            parte=PARTE_CORPO, conteudo=corpo, autor="t", agora=AGORA,
            get_settings=_sv)
