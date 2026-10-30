"""As fases da habilitação de casamento: a conta da régua, e o que a ficha não pode perder.

O QUE ELES DEFENDEM
    Que nenhum quadro fica fora de alcance, e que a tela não trava o que o servidor aceita. Quadro
    sem fase, ou numa aba que não aparece, some da tela sem erro nenhum. A parte de baixo usa o
    sistema de pé, e roda na outra máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import habilitacao_fases as HF  # noqa: E402

FICHA = (RAIZ / "templates" / "rcpn_habilitacao.html").read_text(encoding="utf-8-sig")

CHAVES = (HF.HABILITACAO, HF.EDITAL, HF.PRONTAS, HF.REGISTRO)


def _hab(situacao: str = "EM_ANALISE", **campos) -> dict:
    return {"id": 1, "situacao": situacao, "tipo": "CIVIL", **campos}


def _fase(r: dict, chave: str) -> dict:
    return next(x for x in r["fases"] if x["chave"] == chave)


def _estados(r: dict) -> dict:
    return {x["chave"]: x["estado"] for x in r["fases"]}


def test_quatro_fases_e_o_andamento_sempre():
    r = HF.fases_da_habilitacao(_hab(), andamento=[1, 2])
    assert [x["chave"] for x in r["fases"]] == list(CHAVES)
    assert [x["chave"] for x in r["apoio"]] == [HF.ANDAMENTO]
    assert r["apoio"][0]["contagem"] == 2


def test_os_nomes_sao_os_do_menu():
    """Quem vem de «3 · Prontas para casar» tem de achar a mesma palavra na ficha."""
    menu = (RAIZ / "navegacao.py").read_text(encoding="utf-8")
    r = HF.fases_da_habilitacao(_hab())
    assert _fase(r, HF.PRONTAS)["rotulo"] == "Prontas para casar"
    assert "3 · Prontas para casar" in menu


@pytest.mark.parametrize("situacao, campos, falta, vencida, esperada", [
    ("EM_ANALISE", {}, [1], False, HF.HABILITACAO),
    ("EM_ANALISE", {}, [], False, HF.EDITAL),
    ("COM_OPOSICAO", {}, [], False, HF.EDITAL),
    ("EDITAL_PUBLICADO", {"edital_em": "2026-10-01"}, [], False, HF.EDITAL),
    ("EDITAL_PUBLICADO", {"edital_em": "2026-10-01", "eproclamas_protocolo": "9"}, [], False, HF.PRONTAS),
    ("EDITAL_PUBLICADO", {"edital_em": "2026-10-01", "eproclamas_protocolo": "9"}, [1], False, HF.HABILITACAO),
    ("HABILITADO", {"edital_em": "2026-10-01"}, [], False, HF.PRONTAS),
    ("HABILITADO", {"edital_em": "2026-10-01", "selo": "ABC"}, [], False, HF.REGISTRO),
    ("HABILITADO", {"edital_em": "2026-10-01", "selo": "ABC"}, [], True, HF.PRONTAS),
    ("CELEBRADO", {"edital_em": "2026-10-01", "selo": "ABC"}, [], False, HF.REGISTRO),
    ("ARQUIVADO", {}, [], False, HF.HABILITACAO),
])
def test_abre_no_que_espera_acao(situacao, campos, falta, vencida, esperada):
    r = HF.fases_da_habilitacao(_hab(situacao, **campos), falta=falta, vencida=vencida)
    assert r["inicial"] == esperada


def test_a_conversao_sem_a_uniao_estavel_abre_na_habilitacao():
    h = _hab("EM_ANALISE", tipo="CONVERSAO")
    r = HF.fases_da_habilitacao(h)
    assert r["inicial"] == HF.HABILITACAO
    assert _fase(r, HF.HABILITACAO)["pendencias"] == 1
    assert "união estável" in _fase(r, HF.HABILITACAO)["aviso"]
    com_ela = HF.fases_da_habilitacao(h, uniao_estavel="Processo 12")
    assert com_ela["inicial"] == HF.EDITAL
    assert _fase(com_ela, HF.HABILITACAO)["pendencias"] == 0


def test_o_edital_nao_trava_com_documento_faltando():
    """O impedimento se registra em análise: travar a fase esconderia essa porta."""
    r = HF.fases_da_habilitacao(_hab(), falta=[1, 2])
    edital = _fase(r, HF.EDITAL)
    assert edital["estado"] == HF.LIBERADA and edital["trava"] is None
    assert edital["pendencias"] == 0, "quem está pendente é o documento, e a régua aponta para ele"
    assert _fase(r, HF.HABILITACAO)["pendencias"] == 2


def test_em_analise_trava_expedir_e_registrar():
    r = HF.fases_da_habilitacao(_hab())
    assert _estados(r)[HF.PRONTAS] == HF.TRAVADA
    assert _estados(r)[HF.REGISTRO] == HF.TRAVADA
    assert _fase(r, HF.PRONTAS)["trava"]["ir"] == HF.EDITAL


def test_com_o_edital_publicado_expedir_abre():
    """HOTFIX-2026-10-07-04: o prazo de oposição em curso não impede habilitar."""
    r = HF.fases_da_habilitacao(_hab("EDITAL_PUBLICADO", edital_em="2026-10-01", eproclamas_protocolo="9"))
    assert _estados(r)[HF.PRONTAS] == HF.LIBERADA
    assert _fase(r, HF.PRONTAS)["trava"] is None
    assert _estados(r)[HF.REGISTRO] == HF.TRAVADA
    assert _fase(r, HF.REGISTRO)["trava"]["ir"] == HF.PRONTAS


def test_o_impedimento_nao_decidido_trava_a_certidao():
    r = HF.fases_da_habilitacao(_hab("COM_OPOSICAO", edital_em="2026-10-01"))
    assert _estados(r)[HF.PRONTAS] == HF.TRAVADA
    assert _fase(r, HF.EDITAL)["pendencias"] == 1
    assert _estados(r)[HF.EDITAL] == HF.LIBERADA


def test_habilitado_sem_selo_pede_o_selo_e_ja_deixa_lavrar():
    """A saída de quando o aparelho estava fora do ar: o selo vem depois, e o ato não para."""
    r = HF.fases_da_habilitacao(_hab("HABILITADO", edital_em="2026-10-01", eproclamas_protocolo="9"))
    assert _fase(r, HF.PRONTAS)["pendencias"] == 1
    assert "selo" in _fase(r, HF.PRONTAS)["aviso"].lower()
    assert _estados(r)[HF.REGISTRO] == HF.LIBERADA


def test_a_habilitacao_vencida_nao_deixa_lavrar():
    r = HF.fases_da_habilitacao(_hab("HABILITADO", selo="ABC"), vencida=True)
    assert _estados(r)[HF.REGISTRO] == HF.TRAVADA
    assert _fase(r, HF.REGISTRO)["trava"]["ir"] == HF.PRONTAS
    assert _fase(r, HF.PRONTAS)["pendencias"] == 1


def test_celebrado_fecha_tudo():
    r = HF.fases_da_habilitacao(_hab("CELEBRADO", edital_em="2026-10-01", eproclamas_protocolo="9", selo="ABC"))
    assert set(_estados(r).values()) == {HF.FEITA}
    assert sum(x["pendencias"] for x in r["fases"]) == 0


def test_o_arquivado_nao_cobra_nada_e_aponta_o_andamento():
    r = HF.fases_da_habilitacao(_hab("ARQUIVADO"), falta=[1, 2])
    assert sum(x["pendencias"] for x in r["fases"]) == 0
    assert _estados(r) == {HF.HABILITACAO: HF.LIBERADA, HF.EDITAL: HF.TRAVADA,
                           HF.PRONTAS: HF.TRAVADA, HF.REGISTRO: HF.TRAVADA}
    assert _fase(r, HF.REGISTRO)["trava"]["ir"] == HF.ANDAMENTO


def test_o_arquivado_com_edital_continua_mostrando_o_edital():
    r = HF.fases_da_habilitacao(_hab("ARQUIVADO", edital_em="2026-10-01"))
    assert _fase(r, HF.EDITAL)["trava"] is None
    com_impedimento = HF.fases_da_habilitacao(_hab("ARQUIVADO", oposicao_em="2026-10-01"))
    assert _fase(com_impedimento, HF.EDITAL)["trava"] is None


@pytest.mark.parametrize("situacao", ["EM_ANALISE", "EDITAL_PUBLICADO", "COM_OPOSICAO",
                                      "HABILITADO", "CELEBRADO", "ARQUIVADO"])
@pytest.mark.parametrize("vencida", [False, True])
def test_toda_trava_leva_a_uma_aba_que_existe(situacao, vencida):
    r = HF.fases_da_habilitacao(_hab(situacao), vencida=vencida)
    existem = {x["chave"] for x in r["fases"]} | {x["chave"] for x in r["apoio"]}
    assert r["inicial"] in existem
    assert _estados(r)[r["inicial"]] != HF.TRAVADA, "a ficha não pode abrir numa fase travada"
    for fase in r["fases"]:
        if fase["trava"]:
            assert fase["estado"] == HF.TRAVADA
            assert fase["trava"]["ir"] in existem
            assert fase["trava"]["ir"] != fase["chave"]
        else:
            assert fase["estado"] != HF.TRAVADA


def test_as_situacoes_sao_as_do_processo():
    """Situação nova cairia no fim das contas sem ninguém ver: este teste a chama para cá."""
    hc = (RAIZ / "hc_schema.py").read_text(encoding="utf-8")
    bloco = hc[hc.index("SITUACOES: dict[str, str] = {"):hc.index("# O tipo de casamento")]
    assert set(re.findall(r'^\s+"([A-Z_]+)":', bloco, flags=re.M)) == {
        "EM_ANALISE", "EDITAL_PUBLICADO", "COM_OPOSICAO", "HABILITADO", "CELEBRADO", "ARQUIVADO"}


# ------------------------------------------------------------- o molde

def _sem_marcas(html: str) -> str:
    return re.sub(r"\{%.*?%\}", "", re.sub(r"\{#.*?#\}", "", html, flags=re.S), flags=re.S)


def test_todo_quadro_diz_em_que_fase_mora():
    corpo = _sem_marcas(FICHA[FICHA.index("{% block content %}"):])
    abertos = re.findall(r"<(?:section|details)\b[^>]*\bclass=\"panel[^>]*>", corpo)
    assert len(abertos) >= 13, "o varredor deixou de achar os quadros"
    assert [t for t in abertos if "data-fase" not in t] == []


def test_toda_chave_tem_endereco_e_quadro():
    for chave in (*CHAVES, HF.ANDAMENTO):
        assert f'id="{chave}"' in FICHA, chave
        assert f'data-fase="{chave}"' in FICHA, chave


def test_toda_acao_da_rota_continua_na_ficha():
    """A ficha manda `acao`, e a rota responde: nenhuma pode ter ficado para trás."""
    rota = (RAIZ / "habilitacao_web.py").read_text(encoding="utf-8")
    bloco = rota[rota.index("def _fazer("):rota.index("def rcpn_habilitacao_selar(")]
    da_rota = set(re.findall(r'if acao == "([a-z_]+)"', bloco))
    assert len(da_rota) >= 9, "o varredor deixou de achar as ações"
    assert da_rota == set(re.findall(r'name="acao" value="([a-z_]+)"', FICHA))


def test_celebrar_vem_da_ficha_do_assento_e_cai_no_registro():
    assert 'id="celebracao" data-fase="registro"' in FICHA
    assert "{% if not f or vencida %} id=\"celebracao\"{% endif %}" in FICHA


def test_quem_continua_no_layout_antigo_nao_recebe_nada():
    assert "{% set f = fases_da_ficha() if layout_novo else none %}" in FICHA
    # o quadro só se divide no layout novo
    assert "{% if f and not vencida %}</div></section>" in FICHA
    # e a abertura do quadro novo nunca sai sem o fecho do antigo
    assert FICHA.count("</div></section>") == 1
    assert "{% if f %}{{ travas_e_barras(f) }}</div>{% endif %}" in FICHA


# ------------------------------------------------------------- com o sistema de pé

def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", "ADMIN")
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _layout(c, qual: str) -> None:
    c.post("/preferencias/layout", data={
        "layout": qual, "next": "/", "csrf_token": _token(c.get("/").get_data(as_text=True))})


def _abrir(app) -> int:
    import habilitacao as HAB
    d = app.extensions["db"]
    with d.transaction() as con:
        return int(HAB.abrir(con, {
            "nubente1_nome": "Ana Exemplo", "nubente2_nome": "João Modelo",
            "data_entrada": "2026-10-30"}, agora=d.now(), usuario="Operador Exemplo"))


def test_as_duas_molduras_oferecem_o_mesmo(cg_app):
    c = _entrar(cg_app, "hab_a")
    endereco = f"/rcpn/habilitacoes/{_abrir(cg_app)}"
    acoes = lambda html: sorted(re.findall(r'name="acao" value="([a-z_]+)"', html))  # noqa: E731
    _layout(c, "antigo")
    antigo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-regua" not in antigo
    _layout(c, "novo")
    novo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-regua" in novo
    assert acoes(antigo) == acoes(novo)
    assert len(acoes(novo)) >= 4, "o varredor deixou de achar as ações"
