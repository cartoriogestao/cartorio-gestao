"""A correção do assento em partes: nenhum campo se perde.

O QUE ELES DEFENDEM
    O risco de dividir é um quadro ficar sem parte: ele sumiria da tela sem erro nenhum, e o campo
    de dentro iria junto no envio sem ninguém o ver. A parte de baixo usa o sistema de pé, compara
    as duas molduras e roda na máquina do balcão.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FICHA = (RAIZ / "templates" / "atrib_rcpn_editar.html").read_text(encoding="utf-8-sig")


def _sem_comentarios(html: str) -> str:
    return re.sub(r"\{#.*?#\}", "", html, flags=re.S)


def _partes_das_pessoas() -> dict[str, list[str]]:
    achados = {}
    for lista in re.findall(r"\{% set cg_pessoas = \[(.*?)\] %\}", FICHA):
        chaves = re.findall(r"\('([a-z]+)'", lista)
        achados[re.findall(r", '([^']+)'\)", lista)[0]] = chaves
    return achados


def test_cada_especie_diz_as_suas_pessoas():
    p = _partes_das_pessoas()
    assert set(p) == {"Registrado", "Falecido", "Nubentes", "Pessoas"}
    for rotulo in ("Registrado", "Falecido", "Nubentes"):
        assert p[rotulo] == ["pessoa", "filiacao", "declarante"], rotulo
    assert p["Pessoas"] == ["pessoa"], "espécie sem filiação, como o Livro E, fica com uma parte só"


def test_toda_parte_tem_quadro_e_so_o_motivo_fica_fora():
    corpo = _sem_comentarios(FICHA[FICHA.index("<form"):])
    partes = set(re.findall(r'data-passo="([a-z]+)"', corpo)) | set(re.findall(r"outra_parte\('([a-z]+)'", corpo))
    assert partes == {"assento", "termo", "teor", "pessoa", "filiacao", "declarante"}
    quadros = re.findall(r"<section\b[^>]*>", corpo)
    assert len(quadros) >= 5, "o varredor deixou de achar os quadros"
    assert len([q for q in quadros if "data-passo" not in q]) == 1


def test_as_tres_especies_abrem_as_duas_partes():
    corpo = _sem_comentarios(FICHA)
    assert corpo.count("{% if cg_passos %}{{ outra_parte('filiacao'") == 3
    assert corpo.count("{% if cg_passos %}{{ outra_parte('declarante'") == 3


def test_o_motivo_e_o_botao_ficam_sempre_a_vista():
    corpo = _sem_comentarios(FICHA)
    assert corpo.index('name="motivo"') < corpo.index("data-cg-passos")
    assert "Salvar correções" in corpo[corpo.rindex("</section>"):]


def test_o_campo_obrigatorio_escondido_abre_a_parte_dele():
    script = (RAIZ / "static" / "fases.js").read_text(encoding="utf-8")
    assert 'form.addEventListener("invalid"' in script


def test_quem_continua_no_layout_antigo_nao_recebe_nada():
    assert "{% set cg_passos = none %}" in FICHA
    corpo = _sem_comentarios(FICHA)
    assert corpo.count("outra_parte(") == corpo.count("{% if cg_passos %}{{ outra_parte(") + 1, "só a macro fica de fora"
    assert corpo.count('<div class="cg-passo-bloco"') == corpo.count('{% if cg_passos %}<div class="cg-passo-bloco"')
    assert corpo.count("<nav") == 1
    assert corpo.rindex("{% if cg_passos %}", 0, corpo.index("<nav")) > corpo.index('name="motivo"')


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


def _campos(html: str) -> list[str]:
    inicio = html.index('id="form-da-correcao"')
    return sorted(re.findall(r'name="([^"]+)"', html[inicio:html.index("</form>", inicio)]))


def test_as_duas_molduras_mandam_os_mesmos_campos(cg_app):
    from bd_nativo import banco
    d = cg_app.extensions["db"]
    with d.transaction() as con:
        aid = int(banco(con).escrever(
            """INSERT INTO rc_assentos (serie, especie, nome, situacao, origem, criado_em)
               VALUES ('A', 'NASCIMENTO', 'Ana Exemplo', 'ATIVO', 'MANUAL', %s) RETURNING id""",
            (d.now(),))[0]["id"])
    c = _entrar(cg_app, "editar_a")
    endereco = f"/rcpn/{aid}/editar"
    _layout(c, "antigo")
    antigo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-passos" not in antigo
    _layout(c, "novo")
    novo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-passos" in novo
    assert _campos(antigo) == _campos(novo)
    assert len(_campos(novo)) > 20, "o varredor deixou de achar os campos"
