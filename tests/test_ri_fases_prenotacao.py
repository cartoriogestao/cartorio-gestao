"""As fases da prenotação: a conta da régua, e o que a ficha não pode perder.

O QUE ELES DEFENDEM
    Que nenhum quadro fica fora de alcance. Quadro sem fase, ou numa aba que não aparece,
    some da tela sem erro nenhum. A parte de baixo usa o sistema de pé, e roda na outra máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_fases_prenotacao as RF  # noqa: E402

FICHA = (RAIZ / "templates" / "ri_protocolo_ver.html").read_text(encoding="utf-8-sig")


def _pren(**campos) -> dict:
    return {"id": 1, "situacao": "ABERTO", "selo_prenotacao": "X", **campos}


def _apoio(r: dict) -> list[str]:
    return [x["chave"] for x in r["apoio"]]


def test_tres_fases_e_documentos_sempre():
    r = RF.fases_da_prenotacao(_pren())
    assert [f["chave"] for f in r["fases"]] == [RF.TITULO, RF.EMOLUMENTOS, RF.QUALIFICACAO]
    assert _apoio(r) == [RF.DOCUMENTOS]


def test_apoio_de_lista_vazia_nao_aparece():
    r = RF.fases_da_prenotacao(_pren(), notas=[{"situacao": "RESOLVIDA"}], historico=[1], tem_onr=True)
    assert _apoio(r) == [RF.DOCUMENTOS, RF.NOTAS, RF.ONR, RF.HISTORICO]


def test_abre_no_que_espera_acao():
    assert RF.fases_da_prenotacao(_pren())["inicial"] == RF.TITULO
    assert RF.fases_da_prenotacao(_pren(), documentos=[1])["inicial"] == RF.QUALIFICACAO
    assert RF.fases_da_prenotacao(_pren(), notas=[{"situacao": "ABERTA"}])["inicial"] == RF.QUALIFICACAO
    assert RF.fases_da_prenotacao(_pren(situacao="ENCERRADO"), documentos=[1])["inicial"] == RF.TITULO


def test_nada_trava():
    """O título se confere em qualquer ordem: quem recusa é o servidor."""
    assert all(f["trava"] is None for f in RF.fases_da_prenotacao(_pren())["fases"])


def test_selo_que_falta_e_nota_aberta_marcam_a_regua():
    r = RF.fases_da_prenotacao(_pren(selo_prenotacao=""), notas=[{"situacao": "ABERTA"}])
    pend = {f["chave"]: f["pendencias"] for f in r["fases"]}
    assert pend == {RF.TITULO: 1, RF.EMOLUMENTOS: 0, RF.QUALIFICACAO: 1}


def _sem_comentarios(html: str) -> str:
    return re.sub(r"\{#.*?#\}", "", html, flags=re.S)


def test_todo_quadro_diz_em_que_fase_mora():
    corpo = _sem_comentarios(FICHA[FICHA.index("{% block content %}"):])
    abertos = re.findall(r"<(?:section|details)\b[^>]*\bclass=\"panel[^>]*>", corpo)
    assert len(abertos) >= 8, "o varredor deixou de achar os quadros"
    assert [t for t in abertos if "data-fase" not in t] == []


def test_toda_chave_tem_endereco_e_quadro():
    for chave in (RF.TITULO, RF.EMOLUMENTOS, RF.QUALIFICACAO, RF.DOCUMENTOS, RF.NOTAS, RF.ONR, RF.HISTORICO):
        assert f'id="{chave}"' in FICHA, chave
        assert f'data-fase="{chave}"' in FICHA, chave


def test_quem_continua_no_layout_antigo_nao_recebe_nada():
    assert "{% set f = fases_da_ficha() if layout_novo else none %}" in FICHA
    assert "{% if layout_novo and p.situacao == 'ABERTO' and restam is not none %}" in FICHA


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


def _prenotacao(app) -> int:
    from bd_nativo import banco
    d = app.extensions["db"]
    with d.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO ri_protocolos (numero, livro, data_prenotacao, situacao, criado_em)
               VALUES (%s, '1', %s, 'ABERTO', %s) RETURNING id""",
            (990001, "2026-10-30", d.now()))[0]["id"])


def test_as_duas_molduras_oferecem_o_mesmo(cg_app):
    c = _entrar(cg_app, "pren_a")
    endereco = f"/registro-imoveis/protocolo/{_prenotacao(cg_app)}"
    corpo = lambda html: html[html.index('class="content"'):]        # noqa: E731
    formularios = lambda html: {e for e in re.findall(r'<form[^>]*\baction="([^"]+)"', corpo(html))  # noqa: E731
                                if "/preferencias/" not in e}
    _layout(c, "antigo")
    antigo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-regua" not in antigo
    _layout(c, "novo")
    novo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-regua" in novo
    assert formularios(antigo) == formularios(novo)
