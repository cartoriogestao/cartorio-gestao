"""Writer mínimo XLSX (OOXML) sem openpyxl — só stdlib zipfile+xml."""
from __future__ import annotations

import re
import zipfile
from datetime import date, datetime, time, timedelta
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

# Excel serial: dias desde 1899-12-30 (com bug do Lotus 1900)
_EXCEL_EPOCH = date(1899, 12, 30)


def _excel_date(d: date) -> float:
    return float((d - _EXCEL_EPOCH).days)


def _excel_time(t: time) -> float:
    return (t.hour * 3600 + t.minute * 60 + t.second) / 86400.0


def _xml_t(s: str) -> str:
    return escape(str(s), {"'": "&apos;", '"': "&quot;"})


_COL_RE = re.compile(r"^([A-Z]+)(\d+)$")


def _col_letters(n: int) -> str:
    """1-based column index -> A, B, ..., Z, AA, ..."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _parse_hora_hhmm(texto: str | None) -> time | None:
    if not texto or not str(texto).strip():
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})$", str(texto).strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return time(h, mi)


def _cell_xml(ref: str, value: Any, *, style: int | None = None) -> str:
    s_attr = f' s="{style}"' if style is not None else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s_attr}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}"{s_attr} t="b"><v>{1 if value else 0}</v></c>'
    if isinstance(value, date) and not isinstance(value, datetime):
        return f'<c r="{ref}"{s_attr}><v>{_excel_date(value)}</v></c>'
    if isinstance(value, datetime):
        serial = _excel_date(value.date()) + _excel_time(value.time())
        return f'<c r="{ref}"{s_attr}><v>{serial}</v></c>'
    if isinstance(value, time):
        return f'<c r="{ref}"{s_attr}><v>{_excel_time(value)}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{s_attr}><v>{value}</v></c>'
    # string
    return (
        f'<c r="{ref}"{s_attr} t="inlineStr"><is><t>'
        f"{_xml_t(str(value))}</t></is></c>"
    )


def _sheet_xml(
    rows: list[list[Any]],
    *,
    header_style: int = 1,
    col_styles: dict[int, int] | None = None,
    freeze_header: bool = True,
) -> str:
    col_styles = col_styles or {}
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
    ]
    if rows:
        max_c = max(len(r) for r in rows)
        max_r = len(rows)
        parts.append(
            f'<dimension ref="A1:{_col_letters(max_c)}{max_r}"/>'
        )
    if freeze_header:
        parts.append(
            '<sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
            "</sheetView></sheetViews>"
        )
    parts.append("<sheetData>")
    for r_idx, row in enumerate(rows, start=1):
        parts.append(f'<row r="{r_idx}">')
        for c_idx, val in enumerate(row, start=1):
            ref = f"{_col_letters(c_idx)}{r_idx}"
            if r_idx == 1:
                style = header_style
            else:
                style = col_styles.get(c_idx)
            parts.append(_cell_xml(ref, val, style=style))
        parts.append("</row>")
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><color theme="1"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF0F3D56"/></patternFill></fill>
  </fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf/></cellStyleXfs>
  <cellXfs count="4">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
    <xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
    <xf numFmtId="20" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
  </cellXfs>
</styleSheet>
"""
# style 0 = general, 1 = header, 2 = date (14=mm-dd-yy), 3 = time (20=h:mm)


def build_xlsx(sheets: list[tuple[str, list[list[Any]], dict[int, int] | None]]) -> bytes:
    """sheets: list of (name, rows, col_styles optional)."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
"""
            + "".join(
                f'  <Override PartName="/xl/worksheets/sheet{i}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
                for i in range(1, len(sheets) + 1)
            )
            + "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
""",
        )
        sheets_xml = []
        rels = []
        for i, (name, _rows, _cs) in enumerate(sheets, start=1):
            safe = _xml_t(name[:31] or f"Planilha{i}")
            sheets_xml.append(f'<sheet name="{safe}" sheetId="{i}" r:id="rId{i}"/>')
            rels.append(
                f'<Relationship Id="rId{i}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{i}.xml"/>'
            )
        rels.append(
            '<Relationship Id="rIdStyles" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>'
        )
        zf.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>"""
            + "".join(sheets_xml)
            + "</sheets></workbook>",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
"""
            + "\n".join(rels)
            + "\n</Relationships>\n",
        )
        zf.writestr("xl/styles.xml", _STYLES)
        for i, (_name, rows, col_styles) in enumerate(sheets, start=1):
            zf.writestr(
                f"xl/worksheets/sheet{i}.xml",
                _sheet_xml(rows, col_styles=col_styles or {}),
            )
    return buf.getvalue()


def parse_hora_para_time(texto: str | None) -> time | None:
    return _parse_hora_hhmm(texto)


def parse_data_iso(texto: str | None) -> date | None:
    if not texto:
        return None
    try:
        return date.fromisoformat(str(texto).strip()[:10])
    except ValueError:
        return None
