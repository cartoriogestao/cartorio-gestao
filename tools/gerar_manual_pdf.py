"""Gera o PDF operacional a partir do Markdown indexado por Ajuda e Agente."""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageBreak, PageTemplate,
    Paragraph, Spacer, HRFlowable,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "DOCUMENTACAO" / "MANUAL_OPERACIONAL_DO_SISTEMA.md"
APPENDIX = ROOT / "DOCUMENTACAO" / "MANUAL_TELAS_E_CAMPOS.md"
OUTPUT = ROOT / "output" / "pdf" / "Manual_Operacional_Cartorio_Gestao.pdf"


def _fontes() -> tuple[str, str]:
    font_dir = Path(r"C:\Windows\Fonts")
    regular = font_dir / "arial.ttf"
    bold = font_dir / "arialbd.ttf"
    if regular.is_file() and bold.is_file():
        pdfmetrics.registerFont(TTFont("ManualRegular", str(regular)))
        pdfmetrics.registerFont(TTFont("ManualBold", str(bold)))
        pdfmetrics.registerFontFamily("ManualRegular", normal="ManualRegular", bold="ManualBold")
        return "ManualRegular", "ManualBold"
    return "Helvetica", "Helvetica-Bold"


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r'<font color="#24527A">\1</font>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    return escaped


class ManualDoc(BaseDocTemplate):
    def __init__(self, path: Path, version: str, **kwargs):
        super().__init__(str(path), **kwargs)
        self.version = version
        frame = Frame(23 * mm, 22 * mm, A4[0] - 46 * mm, A4[1] - 44 * mm,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates(PageTemplate(id="manual", frames=[frame], onPage=self._decorate))
        self._outline_count = 0

    def beforeDocument(self):
        self._outline_count = 0

    def _decorate(self, canvas, doc):
        canvas.saveState()
        w, h = A4
        canvas.setStrokeColor(colors.HexColor("#D8E2E9"))
        canvas.line(23 * mm, h - 16 * mm, w - 23 * mm, h - 16 * mm)
        canvas.line(23 * mm, 17 * mm, w - 23 * mm, 17 * mm)
        canvas.setFont("ManualRegular", 8)
        canvas.setFillColor(colors.HexColor("#486171"))
        canvas.drawString(23 * mm, h - 13 * mm, "CARTÓRIO GESTÃO  |  MANUAL OPERACIONAL")
        canvas.drawString(23 * mm, 12 * mm, f"Referência: {self.version}  •  22/09/2026")
        canvas.drawRightString(w - 23 * mm, 12 * mm, str(doc.page))
        canvas.restoreState()

    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, "_manual_heading", None):
            level, title = flowable._manual_heading
            self._outline_count += 1
            key = f"sec{self._outline_count}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, level=level, closed=False)
            if level == 0:
                self.notify("TOCEntry", (0, title, self.page, key))


def build(source: Path = SOURCE, appendix: Path = APPENDIX,
          output: Path = OUTPUT) -> Path:
    regular, bold = _fontes()
    version = (ROOT / "VERSAO.txt").read_text(encoding="utf-8").strip()
    output.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("MTitle", parent=styles["Title"], fontName=bold,
                           fontSize=24, leading=29, textColor=colors.HexColor("#173B52"),
                           alignment=TA_CENTER, spaceAfter=16)
    lead = ParagraphStyle("MLead", fontName=regular, fontSize=10.5, leading=15,
                          textColor=colors.HexColor("#43596A"), alignment=TA_CENTER,
                          spaceAfter=18)
    h1 = ParagraphStyle("MH1", fontName=bold, fontSize=14, leading=18,
                        textColor=colors.HexColor("#173B52"), spaceBefore=17,
                        spaceAfter=8, keepWithNext=True)
    h2 = ParagraphStyle("MH2", fontName=bold, fontSize=11.3, leading=15,
                        textColor=colors.HexColor("#24527A"), spaceBefore=12,
                        spaceAfter=5, keepWithNext=True)
    body = ParagraphStyle("MBody", fontName=regular, fontSize=9.4, leading=14.4,
                          textColor=colors.HexColor("#25343D"), spaceAfter=7,
                          allowWidows=0, allowOrphans=0)
    item = ParagraphStyle("MItem", parent=body, leftIndent=13, firstLineIndent=-8,
                          spaceAfter=5)
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle("TOC0", fontName=regular, fontSize=9,
                                      leading=13, leftIndent=0, firstLineIndent=0,
                                      spaceAfter=3)]
    source_lines = source.read_text(encoding="utf-8").splitlines()
    heading = source_lines[0].removeprefix("# ").strip()
    meta_index = next(i for i, value in enumerate(source_lines[1:], 1) if value.strip())
    story = [Spacer(1, 44 * mm), Paragraph(_inline(heading), title),
             HRFlowable(width="65%", thickness=1.4,
                        color=colors.HexColor("#4B7FA0"), hAlign="CENTER"),
             Spacer(1, 9 * mm), Paragraph(_inline(source_lines[meta_index]), lead),
             Spacer(1, 28 * mm),
             Paragraph("Guia de procedimentos e referência de 264 telas e entradas de menu.", lead),
             PageBreak(), Paragraph("Sumário", h1), toc, PageBreak()]
    for raw in source_lines[meta_index + 1:]:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("# "):
            p = Paragraph(_inline(line[2:]), h1)
            p._manual_heading = (0, line[2:])
            story.append(p)
            continue
        if line.startswith("## "):
            p = Paragraph(_inline(line[3:]), h1)
            p._manual_heading = (0, line[3:])
            story.append(p)
            continue
        if line.startswith("### "):
            p = Paragraph(_inline(line[4:]), h2)
            p._manual_heading = (1, line[4:])
            story.append(p)
            continue
        if re.match(r"^\d+\. ", line):
            story.append(Paragraph(_inline(line), item))
            continue
        if line.startswith("- "):
            story.append(Paragraph("• " + _inline(line[2:]), item))
            continue
        story.append(Paragraph(_inline(line), body))
    if appendix.is_file():
        story.append(PageBreak())
        for raw in appendix.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("# "):
                p = Paragraph(_inline(line[2:]), h1)
                p._manual_heading = (0, line[2:])
                story.append(p)
            elif line.startswith("## "):
                p = Paragraph(_inline(line[3:]), h1)
                p._manual_heading = (0, line[3:])
                story.append(p)
            elif line.startswith("### "):
                p = Paragraph(_inline(line[4:]), h2)
                p._manual_heading = (1, line[4:])
                story.append(p)
            else:
                story.append(Paragraph(_inline(line), body))
    doc = ManualDoc(output, version=version, pagesize=A4,
                    title="Manual completo de operação do Cartório Gestão",
                    author="Cartório Gestão", subject="Procedimentos e referência de telas")
    doc.multiBuild(story)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--appendix", type=Path, default=APPENDIX)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(build(args.source, args.appendix, args.output))
