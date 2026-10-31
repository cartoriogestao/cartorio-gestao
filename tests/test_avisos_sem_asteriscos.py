"""Os avisos não mostram os asteriscos da marcação.

O QUE ELES DEFENDEM
    Nove avisos escrevem `**assim**` e saíam com os asteriscos na tela. O conserto é no molde, e
    não em cada frase: quem escrever o décimo não precisa lembrar. A parte de baixo usa o sistema
    de pé, e roda na outra máquina.
"""
from __future__ import annotations

import re
from pathlib import Path

MOLDES = sorted((Path(__file__).resolve().parent.parent / "templates").glob("base*.html"))


def test_todo_aviso_passa_pelo_filtro():
    assert MOLDES, "o varredor deixou de achar os moldes"
    for molde in MOLDES:
        texto = molde.read_text(encoding="utf-8-sig")
        assert "{{ message }}" not in texto, molde.name
        desenhos = re.findall(r"\{\{\s*message\b[^}]*\}\}", texto)
        assert desenhos, f"{molde.name}: o varredor deixou de achar o aviso"
        assert all("|forte" in d.replace(" ", "") for d in desenhos), molde.name


# ------------------------------------------------------------- com o sistema de pé

def test_o_filtro_marca_e_escapa(cg_app):
    forte = cg_app.jinja_env.filters["forte"]
    assert str(forte("Imprima **o papel**")) == "Imprima <strong>o papel</strong>"
    assert "<script>" not in str(forte("<script>alert(1)</script> **x**"))
