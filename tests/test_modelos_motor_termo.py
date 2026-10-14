# -*- coding: utf-8 -*-
"""Testes do motor de fidelidade — Etapa 2b (termos RC_TERMO_*, creator ODT,
F01 impressão, etiqueta de Notas). Roda sem app.py (Flask mínimo local)."""
from __future__ import annotations

import base64
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures" / "motor_fidelidade"
sys.path.insert(0, str(RAIZ))

import modelos_motor as MOTOR  # noqa: E402
import modelos_motor_web as WEB  # noqa: E402

SV_ENSAIO = {
    "unit_name": "OFÍCIO DE ENSAIO — REGISTRO CIVIL DE PESSOAS NATURAIS",
    "serventia_titular": "OFICIAL DE ENSAIO",
    "serventia_titulo": "Oficial de Registro",
    "ri_cns": "000000",
    "ri_cidade": "Cidade Ensaio",
    "ri_uf": "MA",
    "serventia_endereco": "Rua do Ensaio, nº 1",
}


def _load(nome):
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


def _termo33(**kw):
    t = _load("termo_assento33.json")
    dados = dict(t)
    dados["teor"] = t["teor_congelado"]
    return MOTOR.contexto_termo(dados, sv=SV_ENSAIO,
                                template_id="RC_TERMO_NASCIMENTO", **kw)


# ------------------------------------------------------------ golden termo 33

def test_termo33_golden_congelado():
    t = _load("termo_assento33.json")
    ctx = _termo33()
    texto = ctx["texto"]
    for pedaco in t["esperado_texto_contem"]:
        assert pedaco in texto, pedaco
    for pedaco in t["esperado_texto_nao_contem"]:
        assert pedaco not in texto, pedaco
    assert ctx["fonte_texto"] == "congelado"
    assert ctx["template_id"] == "RC_TERMO_NASCIMENTO"
    assert any("congelado" in a for a in ctx["avisos"])


def test_termo33_raw_2a_fixture_strip_genero_fecho():
    """O teor cru da 2a (nove (9) de setembro (9)…) também sai limpo."""
    t = _load("termo_assento33.json")
    dados = {k: v for k, v in t.items() if k != "teor_congelado"}
    ctx = MOTOR.contexto_termo(dados, sv=SV_ENSAIO)
    texto = ctx["texto"]
    assert "<strong>" not in texto and "<p>" not in texto
    # 2a cru: «sendo filho de MARIA e JOÃO» com registrada F
    assert "sendo filha de MARIA" in texto and "filho de" not in texto
    assert "Eu, OFICIAL DE ENSAIO, Oficial de Registro." in texto
    assert "setembro (9)" not in texto
    assert "nove (09) de setembro de dois mil e vinte e um (2021)" in texto


def test_termo_texto_papel_sem_tags_e_titulo_das_pessoas_naturais():
    ctx = _termo33()
    papel = MOTOR.texto_do_termo(ctx)
    assert "<" not in papel and ">" not in papel
    assert "DAS PESSOAS NATURAIS" in papel
    assert "DE PESSOAS NATURAIS" not in papel
    assert "REGISTRO DE NASCIMENTO" in papel


def test_termo_html_previa_negrito_real_sem_tag_literal():
    ctx = _termo33()
    html = MOTOR.html_do_termo(ctx)
    assert "<strong>BEATRIZ DE EXEMPLO</strong>" in html
    assert "&lt;strong&gt;" not in html
    assert "DAS PESSOAS NATURAIS" in html


def test_termo_genero_masculino_mantem_filho():
    t = _load("termo_assento33.json")
    dados = dict(t, teor=t["teor_congelado"].replace("sendo filho de", "sendo filha de"),
                 sexo="M")
    dados["pessoas"] = [dict(p, sexo="M") if p["papel"] == "REGISTRADO" else p
                        for p in t["pessoas"]]
    ctx = MOTOR.contexto_termo(dados, sv=SV_ENSAIO)
    assert "sendo filho de" in ctx["texto"]
    assert "Inscrito no CPF n.º 000.000.043-40" in ctx["texto"]


def test_termo_fecho_com_escrevente_informado():
    ctx = _termo33(escrevente="ESCREVENTE DE ENSAIO", funcao="Escrevente Autorizada")
    assert "Eu, ESCREVENTE DE ENSAIO, Escrevente Autorizada, dou fé" in ctx["texto"]
    assert ctx["quem_assina"]["escrevente"] == "ESCREVENTE DE ENSAIO"


def test_termo_fecho_sem_quem_assina_avisa_e_nao_inventa():
    t = _load("termo_assento33.json")
    ctx = MOTOR.contexto_termo(dict(t, teor=t["teor_congelado"]), sv={})
    assert "Eu, ____" in ctx["texto"]
    assert any("quem assina" in a for a in ctx["avisos"])


def test_preencher_fecho_nao_mexe_na_linha_de_assinatura_do_acervo():
    texto = "Em testemunho da verdade.\n______________________"
    novo, mudou = MOTOR.preencher_fecho(texto, "FULANO", "Oficial")
    assert not mudou and novo == texto


# 2c: nomes alinhados com o catálogo (`extenso` = dia/ano com algarismo, mês
# só pelo nome); `padrao`/`casa` viraram aliases de `extenso`.
@pytest.mark.parametrize("estilo,esperado", [
    ("extenso", "nove (09) de setembro de dois mil e vinte e um (2021)"),
    ("padrao", "nove (09) de setembro de dois mil e vinte e um (2021)"),
    ("casa", "nove (09) de setembro de dois mil e vinte e um (2021)"),
    ("so_extenso", "nove de setembro de dois mil e vinte e um"),
    ("mes_numerado", "nove (09) de setembro (9) de dois mil e vinte e um (2021)"),
])
def test_data_termo_estilos(estilo, esperado):
    assert MOTOR.data_termo("2021-09-09", estilo=estilo) == esperado
    assert MOTOR.normalizar_datas_no_texto(
        "Em nove (9) de setembro (9) de dois mil e vinte e um,", estilo) == \
        f"Em {esperado},"


def test_data_termo_tres_acentuado_e_maiusculas():
    assert "três (03)" in MOTOR.data_termo("2023-01-03")
    assert MOTOR.normalizar_datas_no_texto("VINTE E TRES DE MAIO DE DOIS MIL") \
        .startswith("VINTE E TRÊS (23) DE MAIO DE DOIS MIL (2000)")
    assert MOTOR.corrigir_tres("VINTE E TRES") == "VINTE E TRÊS"


def test_termo_montado_do_catalogo_sem_teor():
    """Sem teor gravado: monta pelo catálogo da casa e corrige gênero/data."""
    t = _load("termo_assento33.json")
    dados = {k: v for k, v in t.items() if k not in ("teor_congelado", "teor_html_cru")}
    dados.update({"local_fato_nome": "Hospital de Ensaio", "matricula": "0" * 32})
    ctx = MOTOR.contexto_termo(dados, sv=SV_ENSAIO)
    texto = ctx["texto"]
    assert ctx["fonte_texto"] == "montado", ctx["erro"]
    assert "<strong>" not in texto
    assert "sendo filha de MARIA DE EXEMPLO, brasileira" in texto
    assert "Eu, OFICIAL DE ENSAIO, Oficial de Registro, dou fé" in texto
    assert "setembro (9)" not in texto
    assert "Estado do Maranhão" in texto  # Estado vem da UF do cadastro


def test_termo_especie_manda_no_modelo():
    t = _load("termo_assento33.json")
    ctx = MOTOR.contexto_termo(dict(t, teor=t["teor_congelado"]), sv=SV_ENSAIO,
                               template_id="RC_TERMO_OBITO")
    assert ctx["template_id"] == "RC_TERMO_NASCIMENTO"
    assert any("espécie manda" in a for a in ctx["avisos"])


# ------------------------------------------------------------ API termo

@pytest.fixture()
def cliente_motor():
    from flask import Flask
    app = Flask("motor_fidelidade_teste_2b")
    app.config["TESTING"] = True
    WEB.registrar_rotas(app)
    return app.test_client()


def test_api_previa_termo_html(cliente_motor):
    t = _load("termo_assento33.json")
    r = cliente_motor.post("/modelos/api/previa", json={
        "area": "RCPN", "template_id": "RC_TERMO_NASCIMENTO",
        "dados": dict(t, teor=t["teor_congelado"]), "formato": "html",
        "escrevente": "ESCREVENTE DE ENSAIO", "funcao": "Escrevente Autorizada"})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    for k in ("html", "pdf_base64", "paginas", "avisos", "erros",
              "placeholders_usados", "placeholders_desconhecidos"):
        assert k in body
    assert "&lt;strong&gt;" not in body["html"]
    assert "<strong>" not in body["texto"]
    assert "sendo filha de" in body["texto"]
    assert "Eu, ESCREVENTE DE ENSAIO, Escrevente Autorizada" in body["texto"]
    assert "escrevente" in body["placeholders_usados"]


def test_api_previa_area_termo_formato_invalido(cliente_motor):
    r = cliente_motor.post("/modelos/api/previa", json={
        "area": "TERMO", "dados": {}, "formato": "docx"})
    assert r.status_code == 400


def test_api_campos_e_trechos_termo(cliente_motor):
    nomes = {c["nome"] for c in cliente_motor.get(
        "/modelos/api/campos?area=TERMO&tipo=NASCIMENTO").get_json()}
    assert {"escrevente", "funcao_do_escrevente", "teor", "data_do_ato"} <= nomes
    ids = {b["id"] for b in cliente_motor.get(
        "/modelos/api/trechos-bloqueados?area=RCPN&tipo=RC_TERMO_NASCIMENTO").get_json()}
    assert "fecho_termo_rcpn" in ids


# ------------------------------------------------------------ creator ODT

def _odt_falso(meta_creator="Fabiana Neves"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("meta.xml", (
            '<?xml version="1.0" encoding="UTF-8"?><office:document-meta '
            'xmlns:office="o" xmlns:dc="d" xmlns:meta="m"><office:meta>'
            f'<meta:initial-creator>{meta_creator}</meta:initial-creator>'
            '<meta:keyword>Fabiana</meta:keyword><meta:keyword>Sousa</meta:keyword>'
            '<dc:creator>windows</dc:creator></office:meta></office:document-meta>'))
        z.writestr("content.xml", "<x>Oficial de Registro Civil de Pessoas Naturais</x>")
        z.writestr("styles.xml", "<s/>")
    return buf.getvalue()


def test_limpar_autoria_odt_troca_creator_e_titulo():
    odt = MOTOR.limpar_autoria_odt(_odt_falso(), "SERVENTIA X")
    a = MOTOR.autoria_do_odt(odt)
    assert a["dc:creator"] == ["SERVENTIA X"]
    assert a["meta:initial-creator"] == ["SERVENTIA X"]
    assert a["meta:keyword"] == []
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        tudo = b"".join(z.read(n) for n in z.namelist())
        assert z.namelist()[0] == "mimetype"
    assert b"Fabiana" not in tudo and b"Sousa" not in tudo
    assert "Civil das Pessoas Naturais".encode() in tudo


def test_autor_neutro_serventia_ou_sistema():
    assert MOTOR.autor_neutro({"serventia": {"nome": "CASA Y"}}) == "CASA Y"
    assert MOTOR.autor_neutro({}, {"unit_name": "NOME DA SERVENTIA"}) == "Cartório Gestão"
    assert MOTOR.autor_neutro(None, None) == MOTOR.AUTOR_SISTEMA


def test_odt_do_motor_com_molde_real_sem_fabiana():
    molde = RAIZ / "modelos" / "certidao_nascimento_modelo.odt"
    if not molde.is_file():
        pytest.skip("molde .odt ausente nesta árvore de teste")
    nasc = _load("nasc_exemplo.json")
    resp = MOTOR.resposta_previa(area="RCPN", template_id="RC_MOLDE_NASCIMENTO",
                                 dados=nasc, sv=SV_ENSAIO, formato="odt")
    assert resp.get("pdf_base64"), resp.get("erros")
    odt = base64.b64decode(resp["pdf_base64"])
    a = MOTOR.autoria_do_odt(odt)
    assert all("Fabiana" not in v for v in a["dc:creator"] + a["meta:initial-creator"])
    assert a["meta:keyword"] == []
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        content = z.read("content.xml").decode("utf-8")
    assert "Civil de Pessoas Naturais" not in content


def test_odt_do_termo_autoria_neutra():
    try:
        import ri_odt  # noqa: F401
    except Exception:  # noqa: BLE001
        pytest.skip("ri_odt indisponível")
    odt = MOTOR.odt_do_termo(_termo33())
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        tudo = b"".join(z.read(n) for n in z.namelist() if n.endswith(".xml"))
    assert b"Fabiana" not in tudo
    assert b"&lt;strong&gt;" not in tudo


# ------------------------------------------------------------ F01 impressão

def test_html_para_texto_impressao_escape_duplo_e_idempotente():
    f01 = _load("f01_html_cru.json")
    duplo = f01["teor_html"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for entrada in (f01["teor_html"], duplo, "&amp;lt;p&amp;gt;triplo&amp;lt;/p&amp;gt;"):
        texto = MOTOR.html_para_texto_impressao(entrada)
        assert "<" not in texto and "&lt;" not in texto, texto
        assert MOTOR.html_para_texto_impressao(texto) == texto
    assert "MATRÍCULA nº 1" in MOTOR.html_para_texto_impressao(duplo)
    assert MOTOR.html_para_texto_impressao("a < b e c > d") == "a < b e c > d"
    assert MOTOR.html_para_texto_impressao("<script>x()</script><p>ok</p>") == "ok"
    assert MOTOR.sanitizar_teor_para_papel(duplo).startswith("MATRÍCULA")


# ------------------------------------------------------------ etiqueta Notas

def test_etiqueta_titulo_e_virgula_da_data():
    assert MOTOR.titulo_da_etiqueta("autenticacao", 7) == "Etiqueta — autenticação nº 7"
    assert MOTOR.titulo_da_etiqueta("reconhecimento", 9) == "Etiqueta — reconhecimento nº 9"
    assert MOTOR.corrigir_virgula_da_data("X. CIDADE ENSAIO-XX,05/10/2026.") == \
        "X. CIDADE ENSAIO-XX, 05/10/2026."
    assert MOTOR.corrigir_virgula_da_data("CIDADE ENSAIO-XX, 05/10/2026.") == \
        "CIDADE ENSAIO-XX, 05/10/2026."


def test_etiqueta_motor_novo_ganha_espaco_importado_fica_igual():
    novo = MOTOR.texto_da_etiqueta_motor("RECONHEÇO A FIRMA DE X.", "Cidade Ensaio",
                                         "XX", "2026-10-05")
    assert novo.endswith("CIDADE ENSAIO-XX, 05/10/2026.")
    importado = "RECONHEÇO. EM TEST.________ DA VERDADE. CIDADE ENSAIO-XX,19/03/2020."
    assert MOTOR.texto_da_etiqueta_motor(importado, "Cidade Ensaio", "XX",
                                         "2020-03-19") == importado
    e = MOTOR.dados_da_etiqueta_corrigidos(
        {"texto": "Y. EM TEST. DA VERDADE. CIDADE ENSAIO-XX,05/10/2026."},
        tipo="autenticacao", ato_id=3)
    assert e["texto"].endswith("XX, 05/10/2026.")
    assert e["titulo"] == "Etiqueta — autenticação nº 3"


def test_notas_schema_intocado_formato_antigo():
    """Garantia: o motor não alterou `notas_schema.texto_da_etiqueta`."""
    from notas_schema import texto_da_etiqueta
    assert texto_da_etiqueta("A.", "Cidade Ensaio", "XX", "2026-10-05").endswith(
        "CIDADE ENSAIO-XX,05/10/2026.")
