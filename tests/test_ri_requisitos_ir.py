"""A matrícula nova não nasce sem o que o Indicador Real exige — `ri_requisitos_ir` (RI018, 25/11/2026).

O QUE ESTES TESTES PROTEGEM

    a régua é a do arquivo      `ri_requisitos_ir.conferir` é `onr_ir_json.montar_registro_por_campo`,
                                e este dá os mesmos motivos que `montar_registro`

    trava na abertura           matrícula nova sem tipo do imóvel, sem urbano/rural ou com logradouro
                                sem tipo de via não abre; a tela diz o que falta, campo por campo

    UF do município             a UF e a grafia do município saem do cadastro (`ri_municipios_ibge`)

    só avisa                    ficha de acervo; configuração da serventia incompleta

    selo da abertura            não sai para ficha que não sobe

    retificação cadastral       recusa o impedimento que ela cria, e não o que já havia

    claro por preencher         «[NOVA MATRÍCULA]» não vai ao livro; a retificação que o cita, vai

Dados fictícios. Nada aqui fala com o ONR.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_ir_json as J
import ri_minuta as RIMIN
import ri_requisitos_ir as REQ
from bd_nativo import banco

CONFIG = {"ri_cns": "000000", "ri_uf": "MA", "ri_cidade": "Cidade Exemplo",
          "ibge_uf": "21", "ibge_municipio": "99999",
          "ri_municipios_ibge": '{"Riacho Fundo": 2199998}'}

COMPLETA = {"numero": "4015", "livro_norm": "2", "rural_urbano": "U", "tipo_imovel": "Casa",
            "logradouro": "Rua das Flores", "cidade": "Cidade Exemplo", "uf": "MA"}


# ------------------------------------------------------------------ a régua


def test_os_13_tipos_da_tela_sao_os_13_do_manual():
    assert sorted(J.codigo_do_imovel(t) for t in REQ.TIPOS_DO_IMOVEL) == list(range(1, 14))


def test_os_tipos_de_via_da_tela_sao_do_manual_e_nomeiam_a_via():
    assert "Rua" in REQ.TIPOS_DE_VIA and "Fazenda" in REQ.TIPOS_DE_VIA
    assert "Sem" not in REQ.TIPOS_DE_VIA, "«Sem Denominação» não é tipo de via"
    for t in REQ.TIPOS_DE_VIA:
        assert J.partir_logradouro(f"{t} Exemplo")[0] is not None, t


def test_por_campo_da_os_mesmos_motivos_do_gerador():
    casa, _ = J.serventia_de(CONFIG)
    ficha = {"numero": "4015", "livro_norm": "2", "rural_urbano": "", "tipo_imovel": "RURAL",
             "logradouro": "situada na zona rural deste município", "cidade": "Outra", "uf": "PI"}
    _, motivos = J.montar_registro(ficha, casa)
    _, por_campo = J.montar_registro_por_campo(ficha, casa)
    assert motivos == [m for _, m in por_campo]
    assert {c for c, _ in por_campo} == {"rural_urbano", "tipo_imovel", "logradouro", "uf", "cidade"}


def test_ficha_completa_sobe():
    conf = REQ.conferir(COMPLETA, CONFIG)
    assert conf.sobe and conf.pendencias == [] and conf.avisos == []


def test_ficha_como_as_abertas_desde_setembro_nao_sobe_e_diz_por_que():
    conf = REQ.conferir({**COMPLETA, "tipo_imovel": None, "rural_urbano": "R",
                         "logradouro": "situada na zona rural deste município"}, CONFIG)
    assert not conf.sobe
    assert conf.campos() == {"tipo_imovel", "logradouro"}
    assert any("CCIR" in a for a in conf.avisos), "rural sem CCIR avisa, e não trava"


def test_sem_configuracao_nao_trava_e_diz_onde_configurar():
    conf = REQ.conferir(COMPLETA, {"ri_cns": "000000", "ri_uf": "MA"})
    assert conf.pendencias == [] and conf.sem_configuracao
    assert not conf.sobe
    assert "Configurações" in REQ.recado_sem_configuracao(conf)


def test_a_uf_e_a_grafia_saem_do_municipio_do_cadastro():
    saida = REQ.completar_pela_casa({"cidade": "riacho  FUNDO", "uf": None}, CONFIG)
    assert saida == {"cidade": "Riacho Fundo", "uf": "MA"}
    fora = REQ.completar_pela_casa({"cidade": "Outra Cidade", "uf": None}, CONFIG)
    assert fora["uf"] is None, "município de fora não ganha UF"
    assert REQ.municipios_da_casa(CONFIG) == ["Cidade Exemplo", "Riacho Fundo"]
    assert REQ.municipios_da_casa({}) == []


def test_o_tipo_de_via_escolhido_entra_na_frente_uma_vez_so():
    assert REQ.completar_pela_casa({"logradouro": "das Flores"}, CONFIG, tipo_via="Rua")["logradouro"] == "Rua das Flores"
    assert REQ.completar_pela_casa({"logradouro": "Avenida Central"}, CONFIG, tipo_via="Rua")["logradouro"] == "Avenida Central"
    assert REQ.completar_pela_casa({"logradouro": "das Flores"}, CONFIG, tipo_via="Inventada")["logradouro"] == "das Flores"


def test_novos_impedimentos_so_os_que_a_mudanca_cria():
    antes = REQ.conferir({**COMPLETA, "tipo_imovel": None}, CONFIG)
    depois = REQ.conferir({**COMPLETA, "tipo_imovel": None, "rural_urbano": None}, CONFIG)
    assert [p["campo"] for p in REQ.novos_impedimentos(antes, depois)] == ["rural_urbano"]
    assert REQ.novos_impedimentos(antes, antes) == []


# ------------------------------------------------------- claro por preencher


@pytest.mark.parametrize("teor, acervo", [
    ("… da nova matrícula de continuação nº [NOVA MATRÍCULA], fica ENCERRADA …", False),
    ("… nº [NOVA MATRÍCULA], fica ENCERRADA …", True),
    ("CCIR [INSERIR APÓS APRESENTAÇÃO DO DOCUMENTO]", True),
    ("certificação [abb9c01a-0000, conferir]", False),
    ("protocolo nº [NÚMERO DO PROTOCOLO]", False),
])
def test_claro_por_preencher_e_recusado(teor, acervo):
    assert RIMIN.claro_por_preencher(teor, acervo=acervo)


@pytest.mark.parametrize("teor, acervo", [
    ("assinatura [rubrica] do oficial", False),
    ("trecho [ILEGÍVEL] no livro", True),
    ("conforme o R-01 [R-01] e o [CPF] acima", False),
    ('Retifica-se: onde se lê "nº [NOVA MATRÍCULA], fica ENCERRADA", leia-se "nº 4.099, fica ENCERRADA".', False),
])
def test_o_que_nao_e_claro_passa(teor, acervo):
    assert RIMIN.claro_por_preencher(teor, acervo=acervo) is None


# ------------------------------------------------------------------ a tela


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _texto(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


@pytest.fixture()
def s(cg_casa_logada):
    cg_casa_logada["db"].set_settings(CONFIG)
    return cg_casa_logada


def _numeracao(db, proximo: int) -> None:
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("DELETE FROM ri_numeracao WHERE livro=%s", ("2",))
        bd.escrever("""INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso, fixado_em)
                       VALUES (%s,%s,%s,'2026-11-25')""", ("2", proximo, proximo - 1))


def _quantas(db) -> int:
    with db.connect() as con:
        return int(banco(con).um("SELECT COUNT(*) AS n FROM ri_matriculas")["n"])


def _abrir(s, **campos):
    html = s["c"].get("/registro-imoveis/nova").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "area_unidade": "m2", "proprietario_nome": "Fulano Exemplo",
             "georref_situacao": "SEM_OCORRENCIA", **campos}
    return s["c"].post("/registro-imoveis/nova", data=dados, follow_redirects=True).get_data(as_text=True)


def test_a_tela_pede_tipo_do_imovel_e_municipio_do_cadastro(s):
    _numeracao(s["db"], 4015)
    html = s["c"].get("/registro-imoveis/nova").get_data(as_text=True)
    assert 'name="tipo_imovel"' in html and 'name="tipo_via"' in html
    assert "<option selected>Cidade Exemplo</option>" in html and ">Riacho Fundo</option>" in html
    assert re.search(r'name="uf" value="MA" readonly', html)


def test_matricula_nova_sem_os_dados_nao_abre_e_mostra_campo_por_campo(s):
    _numeracao(s["db"], 4015)
    antes = _quantas(s["db"])
    # Urbano: o rural sem CIB já é recusado antes, pela regra do CIB.
    html = _abrir(s, rural_urbano="U", logradouro="situada na zona rural deste município",
                  cidade="Cidade Exemplo")
    assert _quantas(s["db"]) == antes, "abriu matrícula sem o que o Indicador Real exige"
    assert 'id="pendencias-ir"' in html
    assert 'data-campo="tipo_imovel"' in html and 'data-campo="logradouro"' in html
    assert "não foi aberta" in _texto(html)
    # O que foi digitado volta na tela.
    assert "situada na zona rural deste município" in html


def test_matricula_nova_completa_abre_com_tipo_e_uf_do_municipio(s):
    _numeracao(s["db"], 4015)
    _abrir(s, rural_urbano="U", tipo_imovel="Casa", tipo_via="Rua", logradouro="das Flores",
           cidade="Riacho Fundo", uf="PI")
    with s["db"].connect() as con:
        m = banco(con).um("SELECT * FROM ri_matriculas WHERE numero=%s", ("4015",))
    assert m, "a matrícula completa não abriu"
    assert (m["tipo_imovel"], m["logradouro"], m["cidade"], m["uf"]) == ("Casa", "Rua das Flores", "Riacho Fundo", "MA")
    assert REQ.conferir(dict(m), CONFIG).sobe


def test_ficha_de_acervo_abre_e_avisa(s):
    _numeracao(s["db"], 3990)
    html = _abrir(s, logradouro="situada no lugar Exemplo", cidade="Cidade Exemplo")
    with s["db"].connect() as con:
        assert banco(con).um("SELECT id FROM ri_matriculas WHERE numero=%s", ("3990",))
    assert "Ficha de acervo aberta sem o que o Indicador Real exige" in _texto(html)


def test_sem_configuracao_abre_e_avisa(cg_casa_logada):
    s = cg_casa_logada
    _numeracao(s["db"], 4015)
    html = _abrir(s, logradouro="situada no lugar Exemplo", cidade="Cidade Exemplo", uf="MA")
    with s["db"].connect() as con:
        assert banco(con).um("SELECT id FROM ri_matriculas WHERE numero=%s", ("4015",))
    assert "Não deu para conferir os requisitos do Indicador Real" in _texto(html)


def _ficha_nova(db, **campos) -> int:
    linha = {"numero": "4015", "livro": "2", "livro_norm": "2", "tipo_ficha": "ESTRUTURADA",
             "situacao": "ATIVA", "conferido": 1, "origem": "MANUAL", "criado_em": "2026-11-25T10:00:00",
             "rural_urbano": "U", "tipo_imovel": "Casa", "logradouro": "Rua das Flores",
             "cidade": "Cidade Exemplo", "uf": "MA", "encerrada": 0, **campos}
    colunas = ", ".join(linha)
    with db.transaction() as con:
        bd = banco(con)
        mid = bd.escrever(f"INSERT INTO ri_matriculas ({colunas}) VALUES ({', '.join(['%s'] * len(linha))}) RETURNING id",
                          list(linha.values()))[0]["id"]
        bd.escrever("""INSERT INTO ri_partes (matricula_id, ato_id, nome, nome_norm, papel, proprietario,
                       proprietario_ativo, origem) VALUES (%s, NULL, 'Fulano Exemplo', 'fulano exemplo',
                       'proprietario', 1, 1, 'MANUAL')""", (mid,))
    return int(mid)


def test_o_selo_da_abertura_nao_sai_para_ficha_que_nao_sobe(s):
    mid = _ficha_nova(s["db"], tipo_imovel=None)
    ficha = s["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    html = s["c"].post(f"/registro-imoveis/{mid}/selar-abertura", follow_redirects=True,
                       data={"csrf_token": _token(ficha), "codigo_tj": "16.2"}).get_data(as_text=True)
    assert "não saiu" in _texto(html) and "Tipo do imóvel" in _texto(html)
    with s["db"].connect() as con:
        assert not banco(con).um("SELECT selo_abertura_texto FROM ri_matriculas WHERE id=%s", (mid,))["selo_abertura_texto"]


def _editar(s, mid, **campos):
    html = s["c"].get(f"/registro-imoveis/{mid}/editar").get_data(as_text=True)
    versao = re.search(r'name="versao_edicao"[^>]*value="([^"]+)"', html)
    dados = {"csrf_token": _token(html), "motivo": "Conferência com o título apresentado", **campos}
    if versao:
        dados["versao_edicao"] = versao.group(1)
    return s["c"].post(f"/registro-imoveis/{mid}/editar", data=dados, follow_redirects=True).get_data(as_text=True)


def test_a_retificacao_nao_tira_a_ficha_nova_do_indicador(s):
    mid = _ficha_nova(s["db"])
    html = _editar(s, mid, tipo_imovel="")
    assert "Nada foi gravado" in _texto(html)
    with s["db"].connect() as con:
        assert banco(con).um("SELECT tipo_imovel FROM ri_matriculas WHERE id=%s", (mid,))["tipo_imovel"] == "Casa"


def test_a_retificacao_corrige_uma_coisa_sem_exigir_todas(s):
    mid = _ficha_nova(s["db"], tipo_imovel=None, logradouro="situada no lugar Exemplo")
    html = _editar(s, mid, tipo_imovel="Terreno/fração")
    with s["db"].connect() as con:
        assert banco(con).um("SELECT tipo_imovel FROM ri_matriculas WHERE id=%s", (mid,))["tipo_imovel"] == "Terreno/fração"
    assert "ainda não sobe ao Indicador Real" in _texto(html)
    assert 'name="tipo_imovel"' in s["c"].get(f"/registro-imoveis/{mid}/editar").get_data(as_text=True)


def test_a_lavratura_recusa_o_claro_nova_matricula(s):
    mid = _ficha_nova(s["db"])
    ficha = s["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    html = s["c"].post(f"/registro-imoveis/{mid}/atos", follow_redirects=True, data={
        "csrf_token": _token(ficha), "tipo": "AV",
        "teor": "AV-01/4.015 — ENCERRAMENTO. Com a abertura da matrícula nº [NOVA MATRÍCULA], fica "
                "ENCERRADA a presente matrícula."}).get_data(as_text=True)
    assert "[NOVA MATRÍCULA]" in _texto(html) and "Nada foi lavrado" in _texto(html)
    with s["db"].connect() as con:
        assert banco(con).um("SELECT COUNT(*) AS n FROM ri_atos WHERE matricula_id=%s", (mid,))["n"] == 0
