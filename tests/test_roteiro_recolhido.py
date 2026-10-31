"""O roteiro do dia do Protesto no layout novo: o que espera ação abre, o resto recolhe.

O QUE ELES DEFENDEM
    Projeto do novo layout, 30/10/2026. A tela media 7.311 px. O risco é a conduta atrasada vir
    fechada, o link para dentro de algo recolhido não abrir, o formulário do encerramento sumir, ou o
    layout antigo mudar. A parte de baixo usa o sistema de pé, e roda na outra máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

MOLDE = (RAIZ / "templates" / "protesto_painel.html").read_text(encoding="utf-8-sig")


def _dos_blocos(html: str) -> list[tuple[str, bool]]:
    """Cada conduta recolhível na página: a situação, e se ela vem aberta."""
    achados = re.findall(r'<details class="panel rt-conduta s-(\w+)" id="[^"]+"( open)?>', html)
    return [(s, bool(aberta)) for s, aberta in achados]


def _desenhar(condutas):
    """Só o trecho das condutas, no motor de verdade: a regra de quem abre mora no molde."""
    from jinja2 import Environment
    inicio = MOLDE.index("{% set caixa = 'details'")
    fim = MOLDE.index('<p style="margin:8px 0 0"><strong>A conduta:</strong>')
    trecho = MOLDE[inicio:fim].replace("{{ r.rotulo_da_situacao[c.situacao] }}", "{{ c.situacao }}")
    trecho += "</{{ caixa }}></li>{% endfor %}</ol>"
    return Environment().from_string(trecho).render(layout_novo=True, r={"condutas": condutas})


def _conduta(n, situacao):
    return {"n": n, "ancora": f"conduta-{n}", "titulo": f"Conduta {n}", "situacao": situacao,
            "hora_limite": None, "faltam": 0, "atrasados": 0}


def test_abrem_as_atrasadas_e_a_primeira_pendente():
    html = _desenhar([_conduta(1, "FEITO"), _conduta(2, "PENDENTE"), _conduta(3, "ATRASADO"),
                      _conduta(4, "PENDENTE"), _conduta(5, "SEM_MEDIDA"), _conduta(6, "ATRASADO")])
    assert _dos_blocos(html) == [("FEITO", False), ("PENDENTE", True), ("ATRASADO", True),
                                 ("PENDENTE", False), ("SEM_MEDIDA", False), ("ATRASADO", True)]


def test_dia_todo_feito_vem_todo_recolhido():
    html = _desenhar([_conduta(1, "FEITO"), _conduta(2, "FEITO")])
    assert _dos_blocos(html) == [("FEITO", False), ("FEITO", False)]


def test_o_resumo_traz_a_hora_e_a_situacao():
    cabecalho = MOLDE[MOLDE.index("<{{ cabeca }} class=\"rt-cab\">"):MOLDE.index("</{{ cabeca }}>")]
    for parte in ("c.n", "c.titulo", "c.hora_limite", "c.situacao", "c.faltam", "c.atrasados"):
        assert parte in cabecalho, parte


def test_o_layout_antigo_continua_com_o_que_tinha():
    assert "{% set caixa = 'details' if layout_novo else 'section' %}" in MOLDE
    assert "{% set cabeca = 'summary' if layout_novo else 'div' %}" in MOLDE
    assert "{% if not layout_novo %}{{ conferencia_e_envio }}{% endif %}" in MOLDE
    assert '<section class="panel" id="o-que-saiu">' in MOLDE
    assert "<strong>As condutas:</strong>" in MOLDE


def test_a_conferencia_e_o_envio_vem_depois_das_condutas_no_novo():
    assert MOLDE.index("{% endset %}") < MOLDE.index('<ol class="rt-condutas">')
    assert MOLDE.index("</ol>") < MOLDE.index("{% if layout_novo %}{{ conferencia_e_envio }}{% endif %}")


def test_o_link_para_dentro_de_algo_recolhido_abre():
    script = MOLDE[MOLDE.rindex("<script>"):MOLDE.rindex("</script>")]
    assert 'closest("details")' in script
    assert '"hashchange"' in script and '"click"' in script
    assert MOLDE.rindex("{% if layout_novo %}", 0, MOLDE.rindex("<script>")) > MOLDE.index("roteiro-das-centrais")


def test_o_formulario_do_encerramento_continua_dentro_da_conduta():
    assert "url_for('protesto_encerrar_o_dia')" in MOLDE
    assert MOLDE.index('id="encerrar-o-dia"') < MOLDE.index("</{{ caixa }}>")


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


def test_no_layout_novo_o_que_espera_abre(cg_app):
    c = _entrar(cg_app, "roteiro_a")
    _layout(c, "novo")
    html = c.get("/protesto/roteiro").get_data(as_text=True)
    blocos = _dos_blocos(html)
    assert blocos
    assert all(aberta for s, aberta in blocos if s == "ATRASADO")
    assert sum(1 for s, aberta in blocos if s == "PENDENTE" and aberta) <= 1
    assert not any(aberta for s, aberta in blocos if s == "FEITO")
    assert "<strong>As condutas:</strong>" not in html
    assert '<details class="rt-fonte" id="o-que-saiu">' in html
    assert 'id="encerrar-o-dia"' in html


def test_no_layout_antigo_nada_recolhe(cg_app):
    c = _entrar(cg_app, "roteiro_b")
    _layout(c, "antigo")
    html = c.get("/protesto/roteiro").get_data(as_text=True)
    assert not _dos_blocos(html)
    assert '<section class="panel rt-conduta s-' in html
    assert "<strong>As condutas:</strong>" in html
    assert '<section class="panel" id="o-que-saiu">' in html
