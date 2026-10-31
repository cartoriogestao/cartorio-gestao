"""O quadro «Chave da CENPROT» da tela de Configurações.

Ordem do oficial, 30/10/2026: «coloca esse cálculo do xml como uma variável a
ser preenchida pela serventia». Os pesos aqui são fictícios.
"""
from __future__ import annotations

import re

from test_protesto_aviso_web import _token, s  # noqa: F401

import protesto_cenprot as CP

PESOS = "73197319731973197319731"
ROTA = "/configuracoes/cenprot-chave"


def _db(s):  # noqa: F811
    from database import Database
    return Database(s["banco"])


def _chave(sequencial: int, pesos: str = PESOS) -> str:
    return CP.compor_chave(ibge="1234567", sequencial=sequencial, cartorio="03",
                           data="2026-10-30", pesos=pesos)


def _titulo_com_chave(s, chave: str, n: int = 1) -> None:  # noqa: F811
    with _db(s).transaction() as con:
        con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, valor_centavos,
                   saldo_centavos, situacao, chave_cenprot, origem, origem_chave,
                   criado_em)
               VALUES ('DMI', ?, 100, 100, 'APONTADO', ?, 'CRA', ?, 't')""",
            (f"N{n}", chave, f"TESTE:{n}"))


def _salvar(s, **campos):  # noqa: F811
    tela = s["c"].get("/configuracoes").get_data(as_text=True)
    return s["c"].post(ROTA, data={"csrf_token": _token(tela), **campos},
                       follow_redirects=True).get_data(as_text=True)


def test_o_quadro_tem_formulario_proprio_com_token(s):  # noqa: F811
    html = s["c"].get("/configuracoes").get_data(as_text=True)
    form = re.search(rf'<form[^>]*action="{ROTA}"[^>]*>(.*?)</form>', html, re.S)
    assert form, "o quadro da chave sumiu da tela"
    for nome in ("csrf_token", "ibge_uf", "ibge_municipio", "ibge_cartorio",
                 CP.CHAVE_DOS_PESOS):
        assert f'name="{nome}"' in form.group(1)


def test_a_tela_nao_traz_valor_de_fabrica(s):  # noqa: F811
    html = s["c"].get("/configuracoes").get_data(as_text=True)
    campo = re.search(r'<input name="cenprot_chave_pesos".*?value="([^"]*)"',
                      html, re.S)
    assert campo and campo.group(1) == ""


def test_formato_errado_nao_se_grava(s):  # noqa: F811
    html = _salvar(s, cenprot_chave_pesos="123")
    assert "Nada foi gravado" in html
    assert not _db(s).get_setting(CP.CHAVE_DOS_PESOS, "")


def test_conferencia_inteira_grava_e_diz_quantas(s):  # noqa: F811
    _titulo_com_chave(s, _chave(7))
    html = _salvar(s, cenprot_chave_pesos=PESOS)
    assert "1 de 1 chaves" in html
    assert _db(s).get_setting(CP.CHAVE_DOS_PESOS, "") == PESOS


def test_sem_chave_gravada_grava_e_diz_que_nao_ha_o_que_conferir(s):  # noqa: F811
    html = _salvar(s, cenprot_chave_pesos=PESOS)
    assert "Ainda não há chave gravada" in html
    assert _db(s).get_setting(CP.CHAVE_DOS_PESOS, "") == PESOS


def _uma_chave_que_nao_fecha() -> str:
    certa = _chave(7)
    return certa[:14] + str((int(certa[14]) + 1) % 10) + certa[15:]


def test_conferencia_baixa_avisa_e_nao_grava(s):  # noqa: F811
    _titulo_com_chave(s, _uma_chave_que_nao_fecha())
    html = _salvar(s, cenprot_chave_pesos=PESOS, ibge_uf="12")
    assert "0 de 1 chaves" in html
    assert 'name="gravar_mesmo_assim"' in html
    assert PESOS in html, "o que foi digitado não pode se perder"
    assert not _db(s).get_setting(CP.CHAVE_DOS_PESOS, "")
    assert not _db(s).get_setting("ibge_uf", "")


def test_conferencia_baixa_grava_se_a_pessoa_decidir(s):  # noqa: F811
    _titulo_com_chave(s, _uma_chave_que_nao_fecha())
    _salvar(s, cenprot_chave_pesos=PESOS, gravar_mesmo_assim="on")
    assert _db(s).get_setting(CP.CHAVE_DOS_PESOS, "") == PESOS


def test_pesos_vazios_gravam_e_avisam_que_nao_calcula(s):  # noqa: F811
    _db(s).set_settings({CP.CHAVE_DOS_PESOS: PESOS})
    html = _salvar(s, cenprot_chave_pesos="")
    assert "não calcula" in html
    assert _db(s).get_setting(CP.CHAVE_DOS_PESOS, "x") == ""


def test_os_pesos_nao_vao_para_a_auditoria(s):  # noqa: F811
    _salvar(s, cenprot_chave_pesos=PESOS)
    with _db(s).connect() as con:
        linhas = con.execute("SELECT * FROM audit_logs").fetchall()
    assert linhas and all(PESOS not in " ".join(map(str, tuple(x))) for x in linhas)


def test_o_salvar_geral_nao_escreve_o_quadro():
    import inspect

    import app as APP
    fonte = inspect.getsource(APP)
    corpo = fonte[fonte.index("    def settings():"):
                  fonte.index("    def configuracoes_cenprot_chave():")]
    assert "cenprot_chave_pesos" not in corpo


def test_a_tela_do_xml_diz_onde_preencher(s):  # noqa: F811
    html = s["c"].get("/protesto/cenprot-xml").get_data(as_text=True)
    assert "não está calculando a chave" in html
    assert "#cfg-cenprot-chave" in html
    _db(s).set_settings({CP.CHAVE_DOS_PESOS: PESOS})
    html = s["c"].get("/protesto/cenprot-xml").get_data(as_text=True)
    assert "não está calculando a chave" not in html
