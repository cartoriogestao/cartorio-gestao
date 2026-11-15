"""OS DOIS CAMINHOS DO PROTESTO — a integração primeiro, a mão a um clique.

Pedido do oficial em 15/11/2026: *«preciso que o curso manual do protesto seja de
fácil acesso, mas privilegiando a didática do fluxo automatizado por meio das APIs
e o cumprimento do rito dos títulos no cartório»*.

O QUE ESTES TESTES GUARDAM
      - toda conduta do dia, menos o encerramento, diz o passo do rito, o que a
        integração faz e pelo menos um atalho do caminho pela mão, com a
        condição em que ele cabe;
      - **NAO SE INVENTA TELA**: todo atalho monta endereço de verdade, e toda
        âncora existe no molde da tela para onde leva — nos dois layouts;
      - na tela, a integração vem ANTES da mão, e o botão principal fica nela;
      - o curso manual inteiro está no alto do roteiro, na ordem do dia, e a
        lista dos títulos leva a ele;
      - a ficha diz os dois caminhos da fase que espera ação, e só dela; título
        encerrado não tem;
      - nada disto FAZ: são links, e o único formulário do roteiro continua
        sendo o encerramento (`test_protesto_roteiro`).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import protesto_fases as PF
import protesto_roteiro as PR

MOLDES = RAIZ / "templates"
SENHA = "Senha#12345"

# O MOLDE DE CADA TELA QUE RECEBE ÂNCORA. Tela nova com âncora entra aqui: o
# teste recusa âncora cuja tela não esteja mapeada.
MOLDE_DA_TELA = {
    "protesto_retornos": "protesto_retornos.html",
    "protesto_remessas": "protesto_remessas.html",
    "protesto_desistencias": "protesto_desistencias.html",
    "protesto_avisos": "protesto_avisos.html",
    "protesto_instrumentos": "protesto_instrumentos.html",
    "protesto_cenprot_xml": "protesto_cenprot_xml.html",
    "protesto_repasses": "protesto_repasses.html",
}


def _molde(nome: str) -> str:
    return (MOLDES / nome).read_text(encoding="utf-8-sig")


# ------------------------------------------------------------- o catálogo


def test_toda_conduta_menos_o_encerramento_tem_os_dois_caminhos():
    chaves = {c["chave"] for c in PR.CONDUTAS_DO_DIA}
    assert set(PR.CAMINHOS_DA_CONDUTA) == chaves - {"encerrar"}
    for chave, c in PR.CAMINHOS_DA_CONDUTA.items():
        assert c["rito"].strip() and c["integracao"].strip(), chave
        assert c["manual"], chave
        for m in c["manual"]:
            assert m["rotulo"].strip() and m["tela"].strip(), chave
            assert len(m["quando"].strip()) > 30, (chave, m["rotulo"])


def test_o_caminho_manual_sai_na_ordem_do_dia_e_diz_de_que_conduta_e():
    curso = PR.caminho_manual()
    assert [m["conduta_n"] for m in curso] == sorted(m["conduta_n"] for m in curso)
    assert len(curso) == sum(len(c["manual"]) for c in PR.CAMINHOS_DA_CONDUTA.values())
    ancoras = {c["ancora"] for c in PR.CONDUTAS_DO_DIA}
    assert all(m["conduta_ancora"] in ancoras for m in curso)
    # O que o balcão mais procura quando a Central não responde.
    telas = {(m["tela"], m.get("ancora")) for m in curso}
    assert ("protesto_remessas", "receber-pelo-arquivo") in telas
    assert ("protesto_titulo_novo", None) in telas
    assert ("protesto_desistencias", "receber-pelo-arquivo") in telas


def test_a_copia_nao_deixa_a_tela_mexer_no_catalogo():
    c = PR.caminhos_da_conduta("remessa")
    c["manual"][0]["rotulo"] = "outro"
    c["manual"].clear()
    assert PR.CAMINHOS_DA_CONDUTA["remessa"]["manual"][0]["rotulo"] != "outro"
    assert PR.caminhos_da_conduta("encerrar") is None
    assert PR.caminhos_da_conduta("nao-existe") is None


def test_o_manual_nao_usa_homologacao_nem_promete_o_que_o_sistema_nao_prova():
    import json
    tudo = json.dumps(PR.CAMINHOS_DA_CONDUTA, ensure_ascii=False)
    assert "HOMOLOG" not in tudo.upper()
    # A subida pelo site da Central não deixa prova aqui, e o texto diz.
    retorno = PR.CAMINHOS_DA_CONDUTA["retorno"]["manual"][0]["quando"]
    assert "não fica sabendo" in retorno and "encerramento" in retorno


def test_toda_ancora_do_caminho_existe_no_molde_da_tela():
    """Âncora que não existe leva ao alto da tela, e o atalho deixa de ser atalho."""
    vistas = 0
    for chave, c in PR.CAMINHOS_DA_CONDUTA.items():
        for m in c["manual"]:
            if not m.get("ancora"):
                continue
            assert m["tela"] in MOLDE_DA_TELA, (chave, m["tela"])
            texto = _molde(MOLDE_DA_TELA[m["tela"]])
            assert f'id="{m["ancora"]}"' in texto, (chave, m["tela"], m["ancora"])
            vistas += 1
    assert vistas >= 7


def test_a_ancora_dos_quadros_recolhidos_vale_nos_dois_layouts():
    """`protesto_avisos` e `protesto_repasses` trocam `<section>` por `abre(...)` no layout novo."""
    avisos = _molde("protesto_avisos.html")
    for ancora in ("esperando", "nao-entregues", "apontados-sem-aviso"):
        assert f"abre('{ancora}'" in avisos and f'id="{ancora}"' in avisos, ancora
    repasses = _molde("protesto_repasses.html")
    assert "abre('do-balcao'" in repasses and 'id="do-balcao"' in repasses


def test_todo_atalho_monta_endereco_de_verdade(cg_casa):
    from flask import url_for
    app = cg_casa["app"]
    with app.test_request_context():
        for chave, c in PR.CAMINHOS_DA_CONDUTA.items():
            for b in list(c["manual"]) + list(c.get("botoes", ())):
                assert b["tela"] in app.view_functions, (chave, b["tela"])
                url_for(b["tela"], **b["args"])
        for fase, c in PF.CANAIS_DA_FASE.items():
            for _rotulo, tela in list(c["telas"]) + list(c["telas_da_mao"]):
                assert tela in app.view_functions, (fase, tela)
                url_for(tela)


# ------------------------------------------------------------- a ficha


def test_a_ficha_diz_os_canais_da_fase_que_espera_acao():
    assert PF.canais_do_titulo("RECEBIDO")["fase"] == PF.APONTAMENTO
    assert PF.canais_do_titulo("APONTADO")["fase"] == PF.INTIMACAO
    assert PF.canais_do_titulo("INTIMADO", "ANTES")["fase"] == PF.INTIMACAO
    assert PF.canais_do_titulo("INTIMADO", "NO_PRAZO")["fase"] == PF.DESFECHO
    # Depois da lavratura não há dois caminhos, e a serventia já não recebe o pagamento.
    for encerrado in ("PROTESTADO", "PAGO", "DESISTIDO", "CANCELADO", "DEVOLVIDO", ""):
        assert PF.canais_do_titulo(encerrado) is None, encerrado


def test_os_canais_sao_so_das_tres_fases_do_rito():
    assert set(PF.CANAIS_DA_FASE) == {PF.APONTAMENTO, PF.INTIMACAO, PF.DESFECHO}
    intimacao = PF.canais_do_titulo("APONTADO")
    assert {t["tela"] for t in intimacao["telas"]} == {"protesto_resolve", "protesto_ar"}
    assert {t["tela"] for t in intimacao["telas_da_mao"]} == {"protesto_avisos"}
    # A Intimação Digital dá a ciência; quem lavra é a casa.
    assert "ciência" in intimacao["integracao"]


def test_o_molde_da_ficha_poe_os_canais_na_fase_deles():
    ficha = _molde("atrib_protesto_ficha.html")
    assert 'data-canais="{{ canais.fase }}" data-fase="{{ canais.fase }}"' in ficha
    assert ficha.index("data-canais=") < ficha.index('<div class="panel-head"><span>O título</span>')
    bloco = ficha.split("data-canais=", 1)[1].split("</div>", 1)[0]
    assert bloco.index("Pela integração") < bloco.index("Pela mão")
    assert "<form" not in bloco and "<button" not in bloco


# ------------------------------------------------------------- as telas


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


@pytest.fixture()
def s(cg_casa):
    d = cg_casa["app"].extensions["db"]
    d.create_user("caminhos", "Escrevente Exemplo", SENHA, "USER")
    d.set_settings({"modulo_protesto_ligado": "1"})
    c = cg_casa["app"].test_client()
    c.post("/login", data={"username": "caminhos", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def test_o_roteiro_mostra_a_integracao_antes_da_mao_em_cada_conduta(s):
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    for c in PR.CONDUTAS_DO_DIA:
        bloco = html.split(f'id="{c["ancora"]}"', 1)[1].split("</li>", 1)[0]
        if c["chave"] == "encerrar":
            assert "data-caminho=" not in bloco
            continue
        assert "No rito do título:" in bloco, c["chave"]
        a, b = bloco.index('data-caminho="integracao"'), bloco.index('data-caminho="manual"')
        assert a < b, c["chave"]
        # O botão principal é o da integração, e nenhum da mão é principal.
        assert "button primary" in bloco[a:b], c["chave"]
        assert "button primary" not in bloco[b:].split("rt-obrig", 1)[0], c["chave"]


def test_o_curso_manual_esta_no_alto_do_roteiro_com_as_ancoras(s):
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    assert html.index('id="caminho-manual"') < html.index('class="rt-condutas"')
    curso = html.split('id="caminho-manual"', 1)[1].split("</details>", 1)[0]
    assert 'href="/protesto/remessas#receber-pelo-arquivo"' in curso
    assert 'href="/protesto/novo"' in curso
    assert 'href="/protesto/desistencias#receber-pelo-arquivo"' in curso
    assert 'href="/protesto/retornos#arquivos-gerados"' in curso
    assert "<form" not in curso
    assert curso.count("<li") == len(PR.caminho_manual())


def test_a_lista_dos_titulos_leva_ao_curso_manual(s):
    html = s.get("/protesto").get_data(as_text=True)
    assert 'href="/protesto/roteiro#caminho-manual"' in html
    assert 'href="/protesto/novo"' in html
