# -*- coding: utf-8 -*-
"""Testes do motor de fidelidade — Etapa 2c.

`conteudo` não salvo na prévia (termo e molde), placeholders `{{campo}}`,
trechos bloqueados (`marcar_bloqueados`), `arquivo_base64`/`mime`, PDF/ODT do
termo pelo pipeline de emissão do termo, F01 público, hook da versão
publicada do Editor (mock) e login nas APIs. Roda sem app.py.
"""
from __future__ import annotations

import base64
import io
import json
import re
import sys
import types
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures" / "motor_fidelidade"
sys.path.insert(0, str(RAIZ))

import modelos_motor as MOTOR  # noqa: E402
import modelos_motor_placeholders as PH  # noqa: E402
import modelos_motor_versao as VERSAO  # noqa: E402
import modelos_motor_web as WEB  # noqa: E402

SV_ENSAIO = {
    "unit_name": "OFÍCIO DE ENSAIO DO MOTOR",
    "serventia_titular": "OFICIAL DE ENSAIO",
    "serventia_titulo": "Oficial de Registro",
    "ri_cns": "000000",
    "ri_cidade": "Cidade Ensaio",
    "ri_uf": "MA",
    "serventia_endereco": "Rua do Ensaio, nº 1",
}
TERMOS = ("RC_TERMO_NASCIMENTO", "RC_TERMO_CASAMENTO", "RC_TERMO_OBITO",
          "RC_TERMO_LIVRO_E")
MOLDES = {"RC_MOLDE_NASCIMENTO": "certidao_nascimento_modelo.odt",
          "RC_MOLDE_CASAMENTO": "certidao_casamento_modelo.odt",
          "RC_MOLDE_OBITO": "certidao_obito_modelo.odt"}


def _load(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


def _padrao(chave):
    LIVRO = pytest.importorskip("rc_modelos_do_livro")
    return LIVRO.modelo(chave.replace("RC_TERMO_", ""))["texto"]


def _molde(chave):
    p = RAIZ / "modelos" / MOLDES[chave]
    if not p.is_file():
        pytest.skip("molde .odt ausente nesta árvore de teste")
    return p.read_bytes()


def _sem_ri_odt():
    try:
        import ri_odt  # noqa: F401
        return False
    except Exception:  # noqa: BLE001
        return True


@pytest.fixture()
def cliente_motor():
    from flask import Flask
    app = Flask("motor_fidelidade_teste_2c")
    app.config["TESTING"] = True
    WEB.registrar_rotas(app)
    return app.test_client()


# ------------------------------------------------------------ F01 público

def test_f01_fixture_html_para_texto_impressao_publica():
    f01 = _load("f01_html_cru.json")
    assert "html_para_texto_impressao" in MOTOR.__all__
    for chave in ("teor_html", "teor_livro3"):
        bruto = f01[chave]
        duplo = bruto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for entrada in (bruto, duplo):
            texto = MOTOR.html_para_texto_impressao(entrada)
            for tag in f01["esperado_texto_nao_contem"]:
                assert tag not in texto
            assert "&lt;" not in texto
            assert MOTOR.html_para_texto_impressao(texto) == texto
    texto = MOTOR.html_para_texto_impressao(f01["teor_html"])
    for pedaco in f01["esperado_texto_contem"]:
        assert pedaco in texto


def test_f01_corrigir_teor_para_o_patch_ri():
    f01 = _load("f01_html_cru.json")
    duplo = f01["teor_html"].replace("<", "&lt;").replace(">", "&gt;")
    t, fmt = MOTOR.corrigir_teor_f01(duplo, "html")
    assert fmt == "texto" and "<" not in t and "MATRÍCULA nº 1" in t
    t, fmt = MOTOR.corrigir_teor_f01(f01["teor_livro3"], "texto")  # HTML em formato texto
    assert fmt == "texto" and "<p>" not in t
    # HTML real com formato html e texto plano: intocados
    assert MOTOR.corrigir_teor_f01("<p>ok</p>", "html") == ("<p>ok</p>", "html")
    assert MOTOR.corrigir_teor_f01("a < b", "texto") == ("a < b", "texto")
    assert MOTOR.tem_tag_escapada("&amp;lt;p&amp;gt;") is True


# ------------------------------------------------------------ placeholders

def test_normalizar_placeholders_arroba_e_simples_viram_duplo():
    t, conv = MOTOR.normalizar_placeholders(
        "Nome {nome}, CPF @cpf, já {{ cidade_do_ato }}; mail x@exemplo.local")
    assert t == ("Nome {{nome}}, CPF {{cpf}}, já {{cidade_do_ato}}; "
                 "mail x@exemplo.local")
    assert {"de": "@cpf", "para": "{{cpf}}"} in conv
    assert MOTOR.placeholders_do_texto(t) == ["nome", "cpf", "cidade_do_ato"]
    assert MOTOR.para_formato_do_catalogo(t).startswith("Nome {nome}, CPF {cpf}")


def test_analisar_placeholders_usados_e_desconhecidos_termo():
    a = MOTOR.analisar_placeholders(
        "Aos {data_do_ato}, @nome e {{campo_inventado}} e {{serventia.nome}}",
        area="RCPN", template_id="RC_TERMO_NASCIMENTO")
    assert "data_do_ato" in a["placeholders_usados"]
    assert "nome" in a["placeholders_usados"]
    assert a["placeholders_desconhecidos"] == ["campo_inventado"]
    assert "{{nome}}" in a["texto_canonico"]


def test_campos_tem_codigo_e_aliases_e_catalogo_do_termo(cliente_motor):
    lista = cliente_motor.get(
        "/modelos/api/campos?area=RCPN&tipo=RC_TERMO_NASCIMENTO").get_json()
    por_nome = {c["nome"]: c for c in lista}
    assert por_nome["escrevente"]["codigo"] == "{{escrevente}}"
    assert "@escrevente" in por_nome["escrevente"]["aliases"]
    if pytest.importorskip("rc_modelos_do_livro"):
        assert {"declarante_qualificacao", "frase_cpf", "frase_matricula"} <= set(por_nome)


def test_campos_do_molde_trazem_os_marcadores_do_odt():
    _molde("RC_MOLDE_CASAMENTO")
    nomes = {c["nome"] for c in MOTOR.campos(area="RCPN", tipo="RC_MOLDE_CASAMENTO")}
    assert {"conj1_cpf", "regimebens", "matriculacasamento"} <= nomes


# ------------------------------------------------------------ trechos bloqueados

@pytest.mark.parametrize("chave,esperados", [
    ("RC_MOLDE_NASCIMENTO", {"quadro_cnj_anexo_iv", "fecho_certidao_rcpn",
                             "titulo_certidao_nascimento", "matricula_cnj"}),
    ("RC_MOLDE_CASAMENTO", {"quadro_cnj_anexo_v", "fecho_certidao_rcpn",
                            "titulo_certidao_casamento", "rotulo_regime_de_bens"}),
    ("RC_MOLDE_OBITO", {"quadro_cnj_anexo_vi", "fecho_certidao_rcpn",
                        "titulo_certidao_obito", "rotulo_causa_da_morte"}),
    ("RC_TERMO_NASCIMENTO", {"fecho_termo_rcpn", "data_termo_extenso_algarismo"}),
    ("RC_TERMO_CASAMENTO", {"fecho_termo_rcpn", "declaracao_casados_regime"}),
    ("RC_TERMO_OBITO", {"fecho_termo_rcpn", "matricula_cnj"}),
    ("RC_TERMO_LIVRO_E", {"fecho_termo_rcpn"}),
])
def test_trechos_bloqueados_por_modelo(cliente_motor, chave, esperados):
    r = cliente_motor.get(f"/modelos/api/trechos-bloqueados?area=RCPN&tipo={chave}")
    lista = r.get_json()
    ids = {t["id"] for t in lista}
    assert esperados <= ids, ids
    assert all(set(t) >= {"id", "texto", "base_legal", "literal", "marcador"}
               for t in lista)
    assert "quadro_cnj_anexo_iv" not in ids or chave == "RC_MOLDE_NASCIMENTO"


@pytest.mark.parametrize("chave", list(MOLDES))
def test_trechos_literais_existem_no_molde(chave):
    texto = re.sub(r"\s+", " ", PH.texto_do_odt(_molde(chave)))
    for t in MOTOR.trechos_bloqueados(area="RCPN", tipo=chave):
        if t["literal"]:
            assert re.sub(r"\s+", " ", t["texto"]) in texto, t["id"]


@pytest.mark.parametrize("chave", TERMOS)
def test_fecho_do_termo_e_literal_do_catalogo(chave):
    corpo = _padrao(chave)
    fecho = {t["id"]: t for t in MOTOR.trechos_bloqueados(
        area="RCPN", tipo=chave)}["fecho_termo_rcpn"]
    assert fecho["literal"] is True
    assert fecho["texto"] in corpo
    assert "{escrevente}" in fecho["texto"]


# ------------------------------------------------------------ marcar_bloqueados

@pytest.mark.parametrize("chave", TERMOS)
def test_marcar_bloqueados_byte_a_byte_e_idempotente(chave):
    corpo = _padrao(chave)
    marcado = MOTOR.marcar_bloqueados("RCPN", chave, corpo)
    assert "{{#bloqueado fecho_termo_rcpn}}" in marcado
    assert MOTOR.remover_marcadores_bloqueados(marcado) == corpo
    assert MOTOR.marcar_bloqueados("RCPN", chave, marcado) == marcado
    erros, _avisos, ids = MOTOR.conferir_bloqueados("RCPN", chave, marcado)
    assert erros == [] and "fecho_termo_rcpn" in ids
    # com o corpo no formato canônico {{campo}} o trecho também é achado
    canon, _ = MOTOR.normalizar_placeholders(corpo)
    marcado2 = MOTOR.marcar_bloqueados("RCPN", chave, canon)
    assert MOTOR.remover_marcadores_bloqueados(marcado2) == canon
    assert MOTOR.conferir_bloqueados("RCPN", chave, marcado2)[0] == []


def test_bloqueado_adulterado_e_desconhecido():
    corpo = _padrao("RC_TERMO_OBITO")
    marcado = MOTOR.marcar_bloqueados("RCPN", "RC_TERMO_OBITO", corpo)
    mexido = marcado.replace("escrevi e assino", "assino e pronto")
    codigos = {e["codigo"] for e in MOTOR.conferir_bloqueados(
        "RCPN", "RC_TERMO_OBITO", mexido)[0]}
    assert "BLOQUEADO_ADULTERADO" in codigos
    codigos = {e["codigo"] for e in MOTOR.conferir_bloqueados(
        "RCPN", "RC_TERMO_OBITO", "{{#bloqueado nao_existe}}x{{/bloqueado}}")[0]}
    assert "BLOQUEADO_DESCONHECIDO" in codigos


def test_marcar_bloqueados_molde_odt_volta_igual():
    odt = _molde("RC_MOLDE_NASCIMENTO")
    assert MOTOR.marcar_bloqueados("RCPN", "RC_MOLDE_NASCIMENTO", odt) == odt
    b64 = base64.b64encode(odt).decode("ascii")
    assert MOTOR.marcar_bloqueados("RCPN", "RC_MOLDE_NASCIMENTO", b64) == b64


# ------------------------------------------------------------ prévia termo + conteudo

def _dados_termo33_sem_teor():
    t = _load("termo_assento33.json")
    dados = {k: v for k, v in t.items() if k not in ("teor_congelado", "teor_html_cru")}
    dados.update({"local_fato_nome": "Hospital de Ensaio", "matricula": "0" * 32})
    return dados


def _rascunho_nasc():
    corpo = _padrao("RC_TERMO_NASCIMENTO")
    corpo = corpo.replace("Lido e achado conforme",
                          "TEXTO DE RASCUNHO 2C. Lido e achado conforme", 1)
    canon, _ = MOTOR.normalizar_placeholders(corpo)
    canon = canon.replace("{{sexo}}", "@sexo")  # mistura de grafias
    return MOTOR.marcar_bloqueados("RCPN", "RC_TERMO_NASCIMENTO", canon)


def test_previa_termo_conteudo_nao_salvo_substitui_corpo():
    resp = MOTOR.resposta_previa(
        area="RCPN", template_id="RC_TERMO_NASCIMENTO",
        dados=_dados_termo33_sem_teor(), sv=SV_ENSAIO, formato="html",
        conteudo=_rascunho_nasc())
    assert resp["erros"] == [], resp["erros"]
    assert "TEXTO DE RASCUNHO 2C" in resp["texto"]
    assert "bloqueado" not in resp["texto"] and "bloqueado" not in resp["html"]
    assert "{{" not in resp["texto"] and "@sexo" not in resp["texto"]
    assert resp["fonte_texto"] == "montado"
    assert any("não salvo" in a for a in resp["avisos"])
    assert "fecho_termo_rcpn" in resp["bloqueados_presentes"]
    assert {"de": "@sexo", "para": "{{sexo}}"} in resp["conversoes"]
    assert resp["mime"].startswith("text/html")


def test_previa_termo_conteudo_vence_teor_congelado():
    t = _load("termo_assento33.json")
    resp = MOTOR.resposta_previa(
        area="RCPN", template_id="RC_TERMO_NASCIMENTO",
        dados=dict(_dados_termo33_sem_teor(), teor=t["teor_congelado"]),
        sv=SV_ENSAIO, formato="html", conteudo=_rascunho_nasc())
    assert "TEXTO DE RASCUNHO 2C" in resp["texto"]


def test_previa_termo_sem_assento_mostra_claros_e_nao_quebra():
    resp = MOTOR.resposta_previa(
        area="RCPN", template_id="RC_TERMO_NASCIMENTO", dados={},
        sv=SV_ENSAIO, formato="html", conteudo="Aos {{data_do_ato}}, @nome. "
        "Eu, {escrevente}, {funcao_do_escrevente}, dou fé e assino.")
    assert not [e for e in resp["erros"] if e["codigo"] == "TERMO_NAO_MONTOU"]
    # sem ato, o catálogo põe o traço da casa no claro (como a emissão faria);
    # se o catálogo recusar, o motor mostra [campo] — nunca {{campo}} cru
    assert "{{" not in resp["texto"] and "@nome" not in resp["texto"]
    assert "____" in resp["texto"] or "[nome]" in resp["texto"]
    assert "OFICIAL DE ENSAIO" in resp["texto"]
    # sem conteudo e sem dados também não estoura (antes: NameError)
    resp2 = MOTOR.resposta_previa(area="RCPN", template_id="RC_TERMO_OBITO",
                                  dados={}, sv=SV_ENSAIO, formato="html")
    assert resp2["html"]


def test_previa_termo_placeholder_desconhecido_vira_erro(cliente_motor):
    r = cliente_motor.post("/modelos/api/previa", json={
        "area": "RCPN", "template_id": "RC_TERMO_LIVRO_E", "formato": "html",
        "conteudo": "Aos {{data_do_ato}}, {{campo_inventado}}."})
    assert r.status_code == 422
    body = r.get_json()
    assert "campo_inventado" in body["placeholders_desconhecidos"]
    assert any(e["codigo"] == "PLACEHOLDER_DESCONHECIDO" for e in body["erros"])


@pytest.mark.skipif(_sem_ri_odt(), reason="ri_odt indisponível")
@pytest.mark.parametrize("chave", TERMOS)
def test_termo_odt_pelo_pipeline_do_termo_nunca_pelo_molde(monkeypatch, chave):
    import rc_certidao_odt as ODT

    def _proibido(*a, **k):
        raise AssertionError("termo não pode passar pelo molde de certidão")
    monkeypatch.setattr(ODT, "arquivo_da_certidao", _proibido)
    resp = MOTOR.resposta_previa(area="RCPN", template_id=chave, dados={},
                                 sv=SV_ENSAIO, formato="odt")
    assert not resp["erros"], resp["erros"]
    assert resp["mime"] == MOTOR.MIME_ODT
    assert resp["arquivo_base64"] and resp["pdf_base64"] == resp["arquivo_base64"]
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(resp["arquivo_base64"]))) as z:
        content = z.read("content.xml").decode("utf-8")
    assert "bloqueado" not in content and "&lt;strong" not in content


@pytest.mark.skipif(_sem_ri_odt(), reason="ri_odt indisponível")
def test_termo_pdf_ou_odt_com_mime_coerente():
    t = _load("termo_assento33.json")
    resp = MOTOR.resposta_previa(
        area="RCPN", template_id="RC_TERMO_NASCIMENTO",
        dados=dict(t, teor=t["teor_congelado"]), sv=SV_ENSAIO, formato="pdf")
    codigos = {e["codigo"] for e in resp["erros"]}
    assert "ODT_FALHOU" not in codigos
    bruto = base64.b64decode(resp["arquivo_base64"])
    if "PDF_FALHOU" in codigos:  # máquina sem LibreOffice: ODT, mime ODT
        assert resp["mime"] == MOTOR.MIME_ODT and bruto[:2] == b"PK"
    else:
        assert resp["mime"] == MOTOR.MIME_PDF and bruto[:4] == b"%PDF"


# ------------------------------------------------------------ prévia molde + conteudo

def _molde_com_rotulo_trocado(chave, de, para):
    odt = _molde(chave)
    buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(odt)) as zin, zipfile.ZipFile(buf, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "content.xml":
                data = data.decode("utf-8").replace(de, para, 1).encode("utf-8")
            zout.writestr(item, data)
    return buf.getvalue()


def test_previa_molde_conteudo_odt_base64_nao_salvo(cliente_motor):
    rascunho = _molde_com_rotulo_trocado("RC_MOLDE_NASCIMENTO", "NOME:", "NOME RASCUNHO:")
    nasc = _load("nasc_exemplo.json")
    b64 = base64.b64encode(rascunho).decode("ascii")
    r = cliente_motor.post("/modelos/api/previa", json={
        "area": "RCPN", "template_id": "RC_MOLDE_NASCIMENTO", "dados": nasc,
        "formato": "odt", "conteudo": b64})
    body = r.get_json()
    assert r.status_code == 200, body["erros"]
    assert body["mime"] == MOTOR.MIME_ODT
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(body["arquivo_base64"]))) as z:
        content = z.read("content.xml").decode("utf-8")
    assert "NOME RASCUNHO:" in content
    assert "ANA CLARA DE EXEMPLO" in content
    assert "nomenascido" in body["placeholders_usados"]
    assert body["placeholders_desconhecidos"] == []
    assert any("não salvo" in a for a in body["avisos"])
    # HTML do rascunho
    h = MOTOR.resposta_previa(area="RCPN", template_id="RC_MOLDE_NASCIMENTO",
                              dados=nasc, sv=SV_ENSAIO, formato="html", conteudo=b64)
    assert "NOME RASCUNHO:" in h["html"] and "ANA CLARA DE EXEMPLO" in h["html"]
    assert "<text:" not in h["html"]


def test_previa_molde_conteudo_invalido(cliente_motor):
    r = cliente_motor.post("/modelos/api/previa", json={
        "area": "RCPN", "template_id": "RC_MOLDE_OBITO", "formato": "pdf",
        "conteudo": "isto não é um odt"})
    assert r.status_code == 422
    assert any(e["codigo"] == "CONTEUDO_INVALIDO" for e in r.get_json()["erros"])


def test_html_sem_conteudo_tem_mime_html_e_arquivo_nulo():
    resp = MOTOR.resposta_previa(area="RCPN", template_id="RC_MOLDE_NASCIMENTO",
                                 dados=_load("nasc_exemplo.json"), sv=SV_ENSAIO)
    assert resp["mime"].startswith("text/html")
    assert resp["arquivo_base64"] is None and resp["pdf_base64"] is None


# ------------------------------------------------------------ hook versão publicada

class _EditorFalso:
    def __init__(self, ligada=True, pub=None):
        self.ligada, self.pub, self.chamadas = ligada, pub, []

    def chave_ligada(self, con, area="RCPN"):
        self.chamadas.append(("chave_ligada", area))
        return self.ligada

    def conteudo_publicado_se_ligado(self, con, *, area, template_id, parte="CORPO"):
        self.chamadas.append(("publicado", area, template_id, parte))
        return self.pub if self.ligada else None


def test_flag_editor_desligada_por_padrao_e_nem_consulta():
    assert VERSAO.USAR_CONTEUDO_PUBLICADO_EDITOR is False
    ed = _EditorFalso(pub={"conteudo": "X"})
    assert VERSAO.conteudo_publicado_editor(
        object(), template_id="RC_TERMO_NASCIMENTO", editor=ed) is None
    assert ed.chamadas == []


def test_hook_editor_ligado_usa_publicada(monkeypatch):
    pub = {"conteudo": "Aos {{data_do_ato}}, {{#bloqueado fecho_termo_rcpn}}Eu, "
                       "{{escrevente}}, dou fé e assino.{{/bloqueado}}",
           "conteudo_blob": None, "status": "PUBLICADA"}
    ed = _EditorFalso(pub=pub)
    out = VERSAO.conteudo_publicado_editor(
        object(), area="RCPN", template_id="RC_TERMO_NASCIMENTO",
        usar=True, editor=ed)
    assert out["conteudo"] == pub["conteudo"]
    assert ("chave_ligada", "RCPN") in ed.chamadas
    assert ("publicado", "RCPN", "RC_TERMO_NASCIMENTO", "CORPO") in ed.chamadas
    corpo, origem = VERSAO.corpo_do_termo(object(), "RC_TERMO_NASCIMENTO",
                                          usar=True, editor=ed)
    assert origem == VERSAO.ORIGEM_EDITOR
    assert corpo == "Aos {data_do_ato}, Eu, {escrevente}, dou fé e assino."


def test_hook_editor_sem_publicada_ou_chave_desligada_cai_no_corpo_de(monkeypatch):
    casa = types.ModuleType("modelos_da_casa")
    casa.corpo_de = lambda con, chave: f"CORPO VIGENTE {chave}"
    monkeypatch.setitem(sys.modules, "modelos_da_casa", casa)
    for ed in (_EditorFalso(ligada=False, pub={"conteudo": "X"}),
               _EditorFalso(ligada=True, pub=None)):
        corpo, origem = VERSAO.corpo_do_termo(object(), "RC_TERMO_OBITO",
                                              usar=True, editor=ed)
        assert (corpo, origem) == ("CORPO VIGENTE RC_TERMO_OBITO", VERSAO.ORIGEM_ATUAL)
    # flag padrão (desligada): idem, sem consultar o editor
    corpo, origem = VERSAO.corpo_do_termo(object(), "RC_TERMO_OBITO")
    assert origem == VERSAO.ORIGEM_ATUAL


def test_hook_editor_que_quebra_nao_derruba_emissao():
    class _Quebrado:
        def chave_ligada(self, *a, **k):
            raise RuntimeError("editor fora")
    assert VERSAO.conteudo_publicado_editor(
        object(), template_id="RC_MOLDE_OBITO", usar=True, editor=_Quebrado()) is None
    blob, origem = VERSAO.molde_da_certidao(object(), "RC_MOLDE_OBITO", usar=True,
                                            editor=_Quebrado())
    assert blob is None and origem == VERSAO.ORIGEM_ATUAL
    ed = _EditorFalso(pub={"conteudo_blob": b"PK-odt"})
    assert VERSAO.molde_da_certidao(object(), "RC_MOLDE_OBITO", usar=True,
                                    editor=ed) == (b"PK-odt", VERSAO.ORIGEM_EDITOR)


# ------------------------------------------------------------ login nas APIs

def test_login_required_nas_apis_responde_401_json():
    from flask import Flask, redirect
    app = Flask("motor_login_2c")
    app.config["TESTING"] = True
    sessao = {"ok": False}

    def login_required(view):
        def wrapped(*a, **k):
            if not sessao["ok"]:
                return redirect("/login")
            return view(*a, **k)
        return wrapped
    WEB.registrar_rotas(app, None, login_required)
    WEB.registrar_rotas(app, None, login_required)  # 2x não empilha
    c = app.test_client()
    r = c.get("/modelos/api/campos?area=RCPN&tipo=NASCIMENTO")
    assert r.status_code == 401
    assert r.get_json()["erros"][0]["codigo"] == "LOGIN_NECESSARIO"
    sessao["ok"] = True
    assert c.get("/modelos/api/campos?area=RCPN&tipo=NASCIMENTO").status_code == 200
    assert c.get("/modelos/api/trechos-bloqueados?tipo=RC_MOLDE_OBITO").status_code == 200


# ------------------------------------------------------------ estilo de data

def test_estilo_data_alinhado_com_catalogo():
    assert MOTOR.ESTILO_DATA_TERMO == "extenso"
    assert MOTOR.estilo_de_data("padrao") == "extenso"
    assert MOTOR.estilo_de_data("casa") == "extenso"
    assert MOTOR.estilo_de_data("qualquer") == "extenso"
    LIVRO = pytest.importorskip("rc_modelos_do_livro")
    assert LIVRO.data_do_termo("2021-09-09") == MOTOR.data_termo("2021-09-09")
    assert LIVRO.data_do_termo("2026-10-05", com_numeros=True) == \
        MOTOR.data_termo("2026-10-05", com_numeros=True)
