"""O PDF NA TELA SEM A COLUNA DE MINIATURAS — problema #80, 17/09/2026.

A FRASE DO RELATO
    «fica uma coluna de pagina, talvez de gerenciamento de pdf, que nao
     consegue tirar e atrapalha a visualizacao da matricula — tirar essa aba
     de ajuste de pdf», na conferência da ficha da matrícula 4.016.

O QUE SE MEDIU EM 23/09/2026
    A coluna é a barra de miniaturas do VISUALIZADOR DE PDF DO NAVEGADOR: no
    motor do Chrome/Edge, com o quadro largo, ela abre sozinha — com qualquer
    PDF. Conferido com um PDF de teste nos dois jeitos: sem pedido, a coluna
    abre; com `#navpanes=0&pagemode=none` no fim do endereço, não abre, e a
    barra de cima (zoom, imprimir, baixar) continua.

    E UMA SUSPEITA MINHA FOI DESMENTIDA NO CAMINHO: 5 dos 360 PDFs guardados
    (entre eles o da 4.016) foram exportados do Writer com `/PageMode
    /UseOutlines`, que pede o painel lateral, e eu achei que a causa fosse
    essa. O PDF de controle, SEM a marca, abriu com a coluna do mesmo jeito.
    A marca existe; não é ela.

O QUE ESTES TESTES NÃO PROVAM
    Que o Firefox obedece ao pedido — só o motor do Chrome/Edge foi conferido.
"""
from __future__ import annotations

import io
import re
import sqlite3
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
PEDIDO = "#navpanes=0&amp;pagemode=none"
SENHA = "Senha#12345"


def _quadros_que_mostram_arquivo() -> list[tuple[str, int, str]]:
    """(molde, linha, trecho) de todo <iframe> cujo src vem de uma rota.

    As prévias de modelo (`sandbox`, sem `src`) não mostram arquivo e ficam de
    fora por construção: a régua olha só `src="{{ url_for(`.
    """
    achados = []
    for html in sorted((RAIZ / "templates").glob("*.html")):
        texto = html.read_text(encoding="utf-8-sig")
        for m in re.finditer(r"<iframe\b[^>]*?src=\"\{\{\s*url_for\([^\"]*\"",
                             texto, re.S):
            linha = texto.count("\n", 0, m.start()) + 1
            achados.append((html.name, linha, m.group(0)))
    return achados


def test_a_regua_enxerga_os_tres_quadros():
    """Varredor que deixa de achar passa calado. Medido em 23/09/2026: 3."""
    moldes = {molde for molde, _, _ in _quadros_que_mostram_arquivo()}
    assert {"ri_conferir.html", "livro3_conferir.html",
            "rcpj_rtd_titulo.html"} <= moldes


def test_todo_quadro_de_arquivo_pede_para_esconder_a_coluna():
    faltando = [f"{molde}:{linha}" for molde, linha, trecho
                in _quadros_que_mostram_arquivo() if PEDIDO not in trecho]
    assert not faltando, (
        "estes quadros mostram arquivo sem pedir ao visualizador para "
        "esconder a coluna de miniaturas (problema #80):\n    "
        + "\n    ".join(faltando))


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _pdf_minimo() -> bytes:
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


@pytest.fixture()
def casa(cg_casa):
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = cg_casa["cliente"]
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def test_a_conferencia_da_ficha_sai_com_o_pedido_no_quadro(casa):
    """O caso do relato, pela tela: matrícula com digitalização em PDF."""
    con = sqlite3.connect(casa["banco"])
    cur = con.execute(
        """INSERT INTO ri_matriculas
           (numero, livro, livro_norm, situacao, tipo_ficha, cidade, uf,
            descricao_perimetro, origem, criado_em)
           VALUES ('99080', '2', '2', 'ATIVA', 'ESTRUTURADA', 'Cidade Exemplo',
                   'MA', 'Lote teste #80', 'MANUAL', datetime('now'))""")
    mid = int(cur.lastrowid)
    con.commit()
    con.close()

    c = casa["cliente"]
    ficha = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    c.post(f"/registro-imoveis/{mid}/digitalizacao",
           data={"csrf_token": _token(ficha),
                 "arquivo": (io.BytesIO(_pdf_minimo()), "matricula-99080.pdf")},
           content_type="multipart/form-data", follow_redirects=True)

    html = c.get(f"/registro-imoveis/{mid}/conferir-ficha").get_data(as_text=True)
    assert "<iframe" in html, "o PDF não foi mostrado num quadro"
    assert (f"/registro-imoveis/{mid}/digitalizacao/arquivo?visualizar=1"
            f"{PEDIDO}") in html
