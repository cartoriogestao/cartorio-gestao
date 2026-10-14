# -*- coding: utf-8 -*-
"""Testes do motor de fidelidade — Etapa 2a (regressões; 2b em test_modelos_motor_termo.py).

Roda sem registrar o blueprint em app.py (Flask mínimo local).
Golden fixtures: nasc, casamento, óbito cert2/assento32, termo 33, F01.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures" / "motor_fidelidade"
sys.path.insert(0, str(RAIZ))

import modelos_motor as MOTOR  # noqa: E402
import modelos_motor_web as WEB  # noqa: E402


SV_ENSAIO = {
    "unit_name": "SERVENTIA DE ENSAIO DO MOTOR",
    "serventia_titular": "OFICIAL DE ENSAIO",
    "serventia_titulo": "Oficial de Registro",
    "ri_cns": "000000",
    "ri_cidade": "Cidade Ensaio",
    "ri_uf": "XX",
    "serventia_endereco": "Rua do Ensaio, nº 1",
    "serventia_cep": "00.000-000",
    "serventia_telefone": "(00) 0000-0000",
    "serventia_email": "ensaio@exemplo.local",
    "serventia_cnpj": "00.000.000/0001-00",
}


def _load(nome: str) -> dict:
    return json.loads((FIX / nome).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- HTML F01

def test_f01_strip_remove_tags_literais():
    """Documenta F01: HTML cru no papel → helper para 2c."""
    f01 = _load("f01_html_cru.json")
    texto = MOTOR.html_para_texto(f01["teor_html"])
    for pedaco in f01["esperado_texto_contem"]:
        assert pedaco in texto
    for tag in f01["esperado_texto_nao_contem"]:
        assert tag not in texto
    t3 = MOTOR.strip_tags(f01["teor_livro3"])
    assert "Cedula de credito rural" in t3
    assert "<p>" not in t3
    assert MOTOR.parece_html(f01["teor_html"]) is True
    assert MOTOR.parece_html("texto sem marca") is False
    limpo = MOTOR.sanitizar_teor_para_papel(f01["teor_html"])
    assert "<div" not in limpo


# ---------------------------------------------------------------- acento

def test_data_por_extenso_com_tres_acentuado():
    ext = MOTOR.data_por_extenso_acentuada("2020-01-03")
    assert "TRÊS" in ext
    assert "TRES" not in ext.replace("TRÊS", "")
    assert "três" in MOTOR.por_extenso_acentuado(3)


# ---------------------------------------------------------------- nascimento

def test_nascimento_gemeo_caixa_sim_nao_nao_tracos():
    nasc = _load("nasc_exemplo.json")
    ctx = MOTOR.contexto_de_exemplo(nasc, template_id="RC_MOLDE_NASCIMENTO", sv=SV_ENSAIO)
    assert ctx["possuigemeos"] == "NÃO"
    assert ctx["gemeo_caixa"] == "NÃO"
    claros = MOTOR.claros_do_contexto(ctx, sv=SV_ENSAIO)
    assert claros["@possuigemeos"] == "NÃO"
    # traços NÃO vão para a caixa GÊMEO
    assert "----" not in claros["@possuigemeos"]


def test_nascimento_gemeo_sim_quando_ibge():
    nasc = _load("nasc_exemplo.json")
    nasc["ibge_gemeo"] = 2
    nasc["dados"]["strNomeGemeo"] = "IRMAO EXEMPLO"
    ctx = MOTOR.contexto_de_exemplo(nasc, template_id="RC_MOLDE_NASCIMENTO", sv=SV_ENSAIO)
    assert ctx["possuigemeos"] == "SIM"
    assert ctx["nomegemeos"] == "IRMAO EXEMPLO"
    claros = MOTOR.claros_do_contexto(ctx, sv=SV_ENSAIO)
    assert claros["@possuigemeos"] == "SIM"
    assert claros["@nomegemeos"] == "IRMAO EXEMPLO"


def test_nascimento_municipio_nao_e_endereco():
    nasc = _load("nasc_exemplo.json")
    ctx = MOTOR.contexto_de_exemplo(nasc, template_id="RC_MOLDE_NASCIMENTO", sv=SV_ENSAIO)
    assert ctx["municipio_nascimento"] == "Cidade Exemplo"
    assert "Av." not in ctx["municipio_nascimento"]
    assert "nº" not in ctx["municipio_nascimento"].lower()
    assert "Principal" not in ctx["municipio_nascimento"]
    claros = MOTOR.claros_do_contexto(ctx, sv=SV_ENSAIO)
    assert claros["@municipio_nascimento"] == "Cidade Exemplo"


def test_nascimento_cpf_coerente():
    nasc = _load("nasc_exemplo.json")
    ctx = MOTOR.contexto_de_exemplo(nasc, template_id="RC_MOLDE_NASCIMENTO", sv=SV_ENSAIO)
    assert ctx["cpf"] == "000.000.048-55"
    claros = MOTOR.claros_do_contexto(ctx, sv=SV_ENSAIO)
    assert claros["@cpfnascido"] == "000.000.048-55"


def test_nascimento_html_previa_usa_claros_nao_frase_quadro_cnj():
    nasc = _load("nasc_exemplo.json")
    resp = MOTOR.resposta_previa(
        area="RCPN",
        template_id="RC_MOLDE_NASCIMENTO",
        dados=nasc,
        sv=SV_ENSAIO,
        papel="A4",
        formato="html",
    )
    assert not resp["erros"] or all(
        e["codigo"] not in ("FORMATO_INVALIDO",) for e in resp["erros"])
    html = resp["html"] or ""
    assert "sai o quadro CNJ" not in html
    assert "ANA CLARA DE EXEMPLO" in html
    assert "Gêmeo" in html or "GÊMEO" in html.upper() or "NÃO" in html
    assert "Cidade Exemplo" in html
    assert "000.000.048-55" in html
    assert "TRÊS" in html  # 03/01 → três


def test_nascimento_papel_seguranca_sem_brasao():
    nasc = _load("nasc_exemplo.json")
    resp = MOTOR.resposta_previa(
        area="RCPN", template_id="RC_MOLDE_NASCIMENTO",
        dados=nasc, sv=SV_ENSAIO, papel="seguranca", formato="html")
    html = resp["html"] or ""
    assert "brasão" not in html.lower() and "brasao" not in html.lower()
    assert any("fundo branco" in a.lower() or "sem brasão" in a.lower()
               or "sem brasao" in a.lower() for a in resp["avisos"])


# ---------------------------------------------------------------- casamento

def test_casamento_cpf_nos_conjuges():
    cas = _load("casamento_exemplo.json")
    ctx = MOTOR.contexto_de_exemplo(cas, template_id="RC_MOLDE_CASAMENTO", sv=SV_ENSAIO)
    claros = MOTOR.claros_do_contexto(ctx, sv=SV_ENSAIO)
    assert claros["@conj1_cpf"] == "000.000.047-74"
    assert claros["@conj2_cpf"] == "000.000.048-55"
    # não engole com SEM INFORMAÇÃO quando há CPF
    assert "SEM INFORMA" not in claros["@conj1_cpf"].upper()


# ---------------------------------------------------------------- óbito

def test_obito_claros_extras_preparados():
    ob = _load("obito_cert2_assento32.json")
    ctx = MOTOR.contexto_de_exemplo(ob, template_id="RC_MOLDE_OBITO", sv=SV_ENSAIO)
    for campo in ("profissao", "cor_raca", "domicilio", "numero_do", "eleitor"):
        assert campo in ctx
        assert str(ctx[campo]).strip() != ""
    claros = MOTOR.claros_do_contexto(ctx, sv=SV_ENSAIO)
    assert claros["@profissao"].strip() == "agricultor"
    assert claros["@cpffalecido"] == "000.000.047-74"
    assert claros["@municipio_falecimento"] == "Cidade Exemplo"
    assert "TRÊS" in (ctx.get("data_fato_extenso") or "")


def test_obito_html_previa():
    ob = _load("obito_cert2_assento32.json")
    resp = MOTOR.resposta_previa(
        area="RCPN", template_id="RC_MOLDE_OBITO",
        dados=ob, sv=SV_ENSAIO, formato="html")
    html = resp["html"] or ""
    assert "sai o quadro CNJ" not in html
    assert "PEDRO DE EXEMPLO FALECIDO" in html
    assert "agricultor" in html


# ---------------------------------------------------------------- termo (prep 2b)

def test_termo_33_chave_e_strip_strong_literal():
    termo = _load("termo_assento33.json")
    assert MOTOR.chave_termo("NASCIMENTO") == "RC_TERMO_NASCIMENTO"
    texto = MOTOR.html_para_texto(termo["teor_html_cru"])
    assert "<strong>" not in texto
    assert "BEATRIZ DE EXEMPLO" in texto
    # o cru continua cru (strip só tira tag); filho/filha e Eu, ____ são
    # corrigidos no caminho do termo — ver tests/test_modelos_motor_termo.py
    assert "filho de" in texto


# ---------------------------------------------------------------- serventia

def test_nenhum_literal_da_casa_nos_modulos_motor():
    """Guardrail: módulos novos não hardcodam CNS/endereço da serventia.

    A LISTA DO QUE É DA CASA NÃO MORA NESTE TESTE — sanitização B3,
    10/10/2026. Ela trazia o CNPJ, o endereço, o telefone e o CEP desta
    serventia escritos aqui, e o teste que proíbe o literal da casa levaria a
    casa ao repositório público. Quem sabe o que é da casa é o varredor
    `ci/anti_vazamento.py`, com a lista local (`ci/denylist.local.txt`, fora do
    git; no GitHub, o segredo `CG_DENYLIST_LOCAL`) — e sem ela ele continua
    pegando CPF, CNPJ, CNS e selo reais."""
    import ci.anti_vazamento as AV
    deny = AV.denylist_ativa(RAIZ)
    fict = AV.carregar_ficticios(
        RAIZ / "tests" / "fixtures" / "anti_vazamento" / "documentos_ficticios.txt")
    for arq in RAIZ.glob("modelos_motor*.py"):
        achados = AV.varrer_texto(arq.read_text(encoding="utf-8"),
                                  arquivo=arq.name, denylist=deny, ficticios=fict)
        assert not achados, f"{arq.name} contém literal da casa: {achados[0]}"


# ---------------------------------------------------------------- APIs Flask

@pytest.fixture()
def cliente_motor():
    from flask import Flask
    app = Flask("motor_fidelidade_teste")
    app.config["TESTING"] = True
    WEB.registrar_rotas(app)
    return app.test_client()


def test_api_campos(cliente_motor):
    r = cliente_motor.get("/modelos/api/campos?area=RCPN&tipo=NASCIMENTO")
    assert r.status_code == 200
    lista = r.get_json()
    assert isinstance(lista, list) and lista
    nomes = {c["nome"] for c in lista}
    assert "possuigemeos" in nomes
    assert "serventia.nome" in nomes
    assert all(set(c) >= {"nome", "rotulo", "tipo", "obrigatorio", "exemplo", "grupo"}
               for c in lista)


def test_api_trechos_bloqueados(cliente_motor):
    r = cliente_motor.get("/modelos/api/trechos-bloqueados?area=RCPN&tipo=OBITO")
    assert r.status_code == 200
    lista = r.get_json()
    ids = {t["id"] for t in lista}
    assert "quadro_cnj_anexo_vi" in ids
    assert all(set(t) >= {"id", "texto", "base_legal"} for t in lista)


def test_api_previa_html(cliente_motor):
    nasc = _load("nasc_exemplo.json")
    r = cliente_motor.post(
        "/modelos/api/previa",
        json={
            "area": "RCPN",
            "template_id": "RC_MOLDE_NASCIMENTO",
            "dados": nasc,
            "papel": "A4",
            "formato": "html",
        },
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body.get("html")
    assert "sai o quadro CNJ" not in body["html"]
    assert isinstance(body.get("avisos"), list)
    assert isinstance(body.get("erros"), list)
    assert isinstance(body.get("placeholders_usados"), list)


def test_api_previa_formato_invalido(cliente_motor):
    r = cliente_motor.post(
        "/modelos/api/previa",
        json={"area": "RCPN", "template_id": "RC_MOLDE_NASCIMENTO",
              "dados": {}, "formato": "docx"},
    )
    assert r.status_code == 400
    body = r.get_json()
    assert any(e.get("codigo") == "FORMATO_INVALIDO" for e in body.get("erros") or [])


def test_flag_previa_rcpn_desligada():
    """Não ligar emissão/prévia em atribuicoes_web nesta etapa."""
    assert MOTOR.USAR_MOTOR_NA_PREVIA_RCPN is False


def test_odt_quando_molde_existe():
    """Se o molde .odt do pacote existir, ODT da prévia não explode."""
    molde = RAIZ / "modelos" / "certidao_nascimento_modelo.odt"
    if not molde.is_file():
        pytest.skip("molde .odt ausente nesta árvore de teste")
    nasc = _load("nasc_exemplo.json")
    resp = MOTOR.resposta_previa(
        area="RCPN", template_id="RC_MOLDE_NASCIMENTO",
        dados=nasc, sv=SV_ENSAIO, formato="odt")
    # pode ter aviso; não deve ser FORMATO_INVALIDO
    assert resp.get("pdf_base64") or resp.get("html")
