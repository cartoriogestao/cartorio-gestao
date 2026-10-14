from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import ri_modelos_atos as RI  # noqa: E402


NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#0878DF")
PALE_BLUE = colors.HexColor("#EAF4FD")
INK = colors.HexColor("#202326")
MUTED = colors.HexColor("#66717B")
LINE = colors.HexColor("#DDE4EA")
PAPER = colors.HexColor("#F7F8FA")
AMBER = colors.HexColor("#8A5700")
PALE_AMBER = colors.HexColor("#FFF4D8")


def _styles():
    base = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle(
            "Kicker", parent=base["Normal"], fontName="Helvetica-Bold",
            fontSize=8.5, leading=11, textColor=BLUE, spaceAfter=5,
            uppercase=True,
        ),
        "title": ParagraphStyle(
            "Title", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=24, leading=28, textColor=NAVY, alignment=TA_LEFT,
            spaceAfter=5,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle", parent=base["Normal"], fontName="Helvetica",
            fontSize=9, leading=13, textColor=MUTED, spaceAfter=14,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=13, leading=16, textColor=NAVY, spaceBefore=13,
            spaceAfter=7,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.5, leading=14, textColor=INK, spaceAfter=6,
        ),
        "small": ParagraphStyle(
            "Small", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8, leading=11, textColor=MUTED, spaceAfter=4,
        ),
        "document": ParagraphStyle(
            "Document", parent=base["BodyText"], fontName="Times-Roman",
            fontSize=10.2, leading=16, textColor=INK, alignment=TA_LEFT,
        ),
        "callout": ParagraphStyle(
            "Callout", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9, leading=13, textColor=AMBER,
        ),
        "question": ParagraphStyle(
            "Question", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.2, leading=13.5, leftIndent=13, firstLineIndent=-10,
            textColor=INK, spaceAfter=6,
        ),
    }


def _page(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(.5)
    canvas.line(18 * mm, 15 * mm, width - 18 * mm, 15 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18 * mm, 10 * mm, "Cartório Gestão · Revisão dirigida de modelos do RI")
    canvas.drawRightString(width - 18 * mm, 10 * mm, f"Página {doc.page}")
    canvas.restoreState()


def _highlight_model(text: str) -> str:
    text = text.replace("<p>", "").replace("</p>", "")
    text = re.sub(
        r"(\{\{[^{}]+\}\}|\[[^\[\]]+\])",
        r'<font color="#006AC6"><b>\1</b></font>',
        text,
    )
    for label in ("ITBI:", "VALOR DECLARADO PARA FINS DE EMOLUMENTOS:"):
        text = text.replace(f"<b>{label}</b>", f"<br/><br/><b>{label}</b>")
    return text


def _markers(text: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    seen = set()
    for value in re.findall(r"\{\{[^{}]+\}\}|\[[^\[\]]+\]", text):
        if value in seen:
            continue
        seen.add(value)
        kind = "Automático" if value.startswith("{{") else "Preenchimento manual"
        found.append((value, kind))
    return found


def build(output: Path, code: str = "R-COMPRA-VENDA") -> None:
    model = next(item for item in RI.MODELOS if item["codigo"] == code)
    index = RI.MODELOS.index(model) + 1
    styles = _styles()
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = BaseDocTemplate(
        str(output), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=17 * mm, bottomMargin=21 * mm,
        title=f"RI - revisão do modelo {model['nome']}",
        author="Cartório Gestão",
        subject="Espelho para revisão colaborativa do modelo atual do sistema",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id="review", frames=[frame], onPage=_page))

    story = []
    story.append(HRFlowable(width="100%", thickness=4, color=BLUE, spaceAfter=12))
    story.append(Paragraph("REGISTRO DE IMÓVEIS · MODELO 01", styles["kicker"]))
    story.append(Paragraph("Registro - Compra e venda", styles["title"]))
    story.append(Paragraph(
        f"Código interno: <b>{model['codigo']}</b> · posição {index} de {len(RI.MODELOS)} "
        "na biblioteca de atos · espelho do padrão de fábrica da versão 3.6.68",
        styles["subtitle"],
    ))

    notice = Table([[Paragraph(
        "<b>Para nossa revisão.</b> Este PDF reproduz o texto atualmente previsto no "
        "sistema. Nenhuma alteração foi aplicada ao modelo. Os trechos em azul são "
        "campos preenchidos pelo sistema ou pelo escrevente.", styles["callout"])]],
        colWidths=[doc.width])
    notice.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_AMBER),
        ("BOX", (0, 0), (-1, -1), .7, colors.HexColor("#E6C66D")),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.extend([notice, Spacer(1, 7)])

    facts = Table([
        [Paragraph("Natureza", styles["small"]), Paragraph("Fundamentação indicada no sistema", styles["small"])],
        [Paragraph(f"<b>{model['natureza']}</b>", styles["body"]),
         Paragraph(model["fundamentacao"], styles["body"])],
    ], colWidths=[48 * mm, doc.width - 48 * mm])
    facts.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PAPER),
        ("BOX", (0, 0), (-1, -1), .6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), .35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([facts, Paragraph("Texto atual do modelo", styles["h2"])])

    model_box = Table([[Paragraph(_highlight_model(model["corpo"]), styles["document"])]],
                      colWidths=[doc.width])
    model_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), .8, LINE),
        ("LINEBEFORE", (0, 0), (0, -1), 3, BLUE),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 13),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 13),
    ]))
    story.append(model_box)
    story.append(Paragraph(
        "Nota de forma: o sistema grava o ato em texto corrido; as quebras acima apenas "
        "separam blocos informativos para facilitar esta leitura.", styles["small"]))

    story.append(Paragraph("Claros e fontes de preenchimento", styles["h2"]))
    marker_rows = [[Paragraph("Marcador", styles["small"]), Paragraph("Origem", styles["small"])]]
    for marker, kind in _markers(model["corpo"]):
        marker_rows.append([
            Paragraph(marker.replace("{{", "&#123;&#123;").replace("}}", "&#125;&#125;"), styles["body"]),
            Paragraph(kind, styles["body"]),
        ])
    markers = Table(marker_rows, colWidths=[doc.width * .63, doc.width * .37], repeatRows=1)
    markers.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
        ("BOX", (0, 0), (-1, -1), .6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), .3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(markers)

    story.append(Paragraph("Conferências previstas antes de lavrar", styles["h2"]))
    for number, requirement in enumerate(model["requisitos"], 1):
        story.append(Paragraph(f"<b>{number}.</b> {requirement}", styles["question"]))

    story.append(Paragraph("Pontos para decidirmos juntos", styles["h2"]))
    questions = [
        "A expressão de abertura deve continuar como “Pela escritura pública lavrada...” ou a casa usa outra fórmula?",
        "A qualificação de vendedores e compradores já vem completa do cadastro ou deve haver um bloco explícito no modelo?",
        "Preço, valor de avaliação, ITBI e base de emolumentos devem aparecer nesta ordem?",
        "Devemos identificar o título com livro e folhas, protocolo eletrônico ou ambos?",
        "Qual fórmula de encerramento e assinatura deve ser compartilhada pelos atos de registro?",
    ]
    for number, question in enumerate(questions, 1):
        story.append(Paragraph(f"<font color='#0878DF'><b>{number:02d}</b></font> &nbsp;{question}", styles["question"]))

    story.append(Spacer(1, 8))
    next_box = Table([[Paragraph(
        "<b>Próximo passo:</b> diga o que deseja mudar neste modelo. Depois da sua "
        "aprovação, atualizamos o texto no sistema e passamos ao próximo modelo da sequência.",
        styles["body"]) ]], colWidths=[doc.width])
    next_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
        ("BOX", (0, 0), (-1, -1), .7, colors.HexColor("#A8D0F2")),
        ("LEFTPADDING", (0, 0), (-1, -1), 11),
        ("RIGHTPADDING", (0, 0), (-1, -1), 11),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
    ]))
    story.append(KeepTogether([next_box]))

    doc.build(story)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "output" / "pdf" / "RI_01_Registro_Compra_e_Venda.pdf"
    build(target)
    print(target.resolve())
