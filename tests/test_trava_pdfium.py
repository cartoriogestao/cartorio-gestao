"""Uma trava só para o PDFium do sistema inteiro (16/11/2026).

O PDFium não aguenta duas linhas de execução ao mesmo tempo: na produção, a
leitura por IA de um óbito caiu com «OSError: access violation», e o mesmo erro
aparecia na miniatura do RI e na prévia do teor do RTD. Cada módulo tinha a sua
trava — ou nenhuma —, e uma não segurava a outra. Ver `trava_pdfium`.
"""
from __future__ import annotations

import ast
import io
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

import trava_pdfium as TP

RAIZ = Path(__file__).resolve().parent.parent
NOMES_DA_TRAVA = {"TRAVA", "TRAVA_DO_PDFIUM", "_PDFIUM"}


def _modulos_com_pdfium() -> list[Path]:
    return sorted(p for p in RAIZ.glob("*.py")
                  if "PdfDocument(" in p.read_text(encoding="utf-8", errors="replace"))


def _aberturas_fora_da_trava(arquivo: Path) -> list[int]:
    """Linhas com `….PdfDocument(…)` que não estão dentro de `with <trava>:`."""
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    soltas: list[int] = []

    def visitar(no, travado: bool):
        if isinstance(no, ast.With):
            travado = travado or any(
                isinstance(item.context_expr, ast.Name)
                and item.context_expr.id in NOMES_DA_TRAVA
                for item in no.items)
        if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                and no.func.attr == "PdfDocument" and not travado):
            soltas.append(no.lineno)
        for filho in ast.iter_child_nodes(no):
            visitar(filho, travado)

    visitar(arvore, False)
    return soltas


def test_todo_pdfdocument_do_sistema_abre_dentro_da_trava():
    modulos = _modulos_com_pdfium()
    # Os seis que existiam em 16/11/2026; um novo entra na conta sozinho.
    assert {"revisao_anexos.py", "revisao_transcricao.py", "ri_digitalizacao.py",
            "impressao_pdf.py", "rg_teor_rtdpj.py", "notas_web.py"} <= {p.name for p in modulos}
    soltas = {p.name: _aberturas_fora_da_trava(p) for p in modulos}
    assert {nome: linhas for nome, linhas in soltas.items() if linhas} == {}


def test_a_trava_e_uma_so_no_sistema_inteiro():
    import impressao_pdf
    import revisao_anexos
    import revisao_transcricao
    import rg_teor_rtdpj
    import ri_digitalizacao

    assert revisao_anexos._PDFIUM is TP.TRAVA
    assert revisao_transcricao._PDFIUM is TP.TRAVA
    for modulo in (ri_digitalizacao, impressao_pdf, rg_teor_rtdpj):
        assert modulo.TRAVA_DO_PDFIUM is TP.TRAVA


def test_a_trava_aceita_a_mesma_linha_de_novo():
    with TP.TRAVA:
        with TP.TRAVA:      # uma função travada chamando outra: não se prende
            pass


# ------------------------------------------------------------ com o PDFium


def _pdf_de_paginas(n: int) -> bytes:
    """PDF de `n` páginas, cada uma com um tom de cinza diferente — uma imagem
    trocada entre linhas aparece como tom errado."""
    paginas = []
    for i in range(n):
        im = Image.new("RGB", (300, 400), (40 * i % 256,) * 3)
        ImageDraw.Draw(im).rectangle((20, 20, 120, 120), fill=(255, 255, 255))
        paginas.append(im)
    saida = io.BytesIO()
    paginas[0].save(saida, format="PDF", save_all=True, append_images=paginas[1:])
    return saida.getvalue()


def test_imagem_pil_nao_depende_do_bitmap_fechado():
    pdfium = pytest.importorskip("pypdfium2")
    with TP.TRAVA:
        doc = pdfium.PdfDocument(_pdf_de_paginas(2))
        try:
            imagem = TP.imagem_pil(doc[1], scale=0.5, grayscale=True)
        finally:
            doc.close()
    # Documento e bitmap fechados: a imagem ainda se lê inteira.
    assert imagem.size == (150, 200)
    assert imagem.getpixel((140, 190)) == 40


def test_miniatura_do_ri_e_teor_do_rtd_ao_mesmo_tempo_sem_erro_nem_troca(tmp_path: Path):
    pytest.importorskip("pypdfium2")
    import rg_teor_rtdpj
    import ri_digitalizacao

    arquivos = []
    for k in range(4):
        caminho = tmp_path / f"doc{k}.pdf"
        caminho.write_bytes(_pdf_de_paginas(3 + k))
        arquivos.append(caminho)

    def miniatura(c):
        return ri_digitalizacao.miniatura_png(c, largura=150)

    def teor(c):
        return [im.tobytes() for im in rg_teor_rtdpj._paginas_de_pdf(c)]

    esperado = {(f, c): f(c) for f in (miniatura, teor) for c in arquivos}
    tarefas = [(f, c) for _ in range(6) for f in (miniatura, teor) for c in arquivos]
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(lambda t: (t, t[0](t[1])), tarefas))
    trocadas = [t for t, r in resultados if r != esperado[t]]
    assert trocadas == []
