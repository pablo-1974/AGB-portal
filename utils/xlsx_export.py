"""Exportación XLSX en memoria (stdlib). Sin openpyxl ni archivos en %TEMP%."""

from __future__ import annotations

import zipfile
from io import BytesIO
from xml.sax.saxutils import escape

# API usada por listados (comprobar en consola al arrancar)
LISTADOS_XLSX_API = "stdlib-zip"


def _col_letter(index: int) -> str:
    n = index + 1
    letters = ""
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _inline_cell(row: int, col: int, value: object) -> str:
    ref = f"{_col_letter(col)}{row}"
    text = escape("" if value is None else str(value))
    return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'


def _sheet_xml(headers: list[str], rows: list[list[object]]) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    cells = [_inline_cell(1, i, h) for i, h in enumerate(headers)]
    parts.append(f'<row r="1">{"".join(cells)}</row>')
    for row_idx, row in enumerate(rows, start=2):
        cells = [_inline_cell(row_idx, col_idx, val) for col_idx, val in enumerate(row)]
        parts.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    parts.extend(["</sheetData>", "</worksheet>"])
    return "".join(parts)


def _workbook_xml(sheet_name: str) -> str:
    title = escape((sheet_name or "Hoja")[:31])
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets><sheet name=\"{title}\" sheetId=\"1\" r:id=\"rId1\"/></sheets>"
        "</workbook>"
    )


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>"""


def simple_table_xlsx_bytes(
    *,
    sheet_name: str,
    headers: list[str],
    rows: list[list[object]],
) -> bytes:
    """Genera un .xlsx mínimo solo en RAM (zip + XML)."""
    if not headers:
        raise ValueError("La tabla Excel necesita al menos un encabezado.")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _ROOT_RELS)
        zf.writestr("xl/workbook.xml", _workbook_xml(sheet_name))
        zf.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        zf.writestr("xl/worksheets/sheet1.xml", _sheet_xml(headers, rows))
        zf.writestr("xl/styles.xml", _STYLES)

    data = buf.getvalue()
    if len(data) < 32:
        raise ValueError("El Excel generado está vacío")
    return data


_CONTENT_TYPES_2 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>"""

_WORKBOOK_RELS_2 = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _workbook_xml_two_sheets(sheet1: str, sheet2: str, *, sheet2_hidden: bool = False) -> str:
    t1 = escape((sheet1 or "Hoja1")[:31])
    t2 = escape((sheet2 or "Hoja2")[:31])
    state = ' state="hidden"' if sheet2_hidden else ""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        f'<sheet name="{t1}" sheetId="1" r:id="rId1"/>'
        f'<sheet name="{t2}" sheetId="2"{state} r:id="rId2"/>'
        "</sheets>"
        "</workbook>"
    )


def _sheet_xml_from_rows(rows: list[list[object]]) -> str:
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for row_idx, row in enumerate(rows, start=1):
        cells = [_inline_cell(row_idx, col_idx, val) for col_idx, val in enumerate(row)]
        parts.append(f'<row r="{row_idx}">{"".join(cells)}</row>')
    parts.extend(["</sheetData>", "</worksheet>"])
    return "".join(parts)


def two_sheets_xlsx_bytes(
    *,
    sheet1_name: str,
    sheet1_rows: list[list[object]],
    sheet2_name: str,
    sheet2_rows: list[list[object]],
    sheet2_hidden: bool = False,
) -> bytes:
    """Dos hojas .xlsx en RAM (p. ej. datos + _meta oculta)."""
    if not sheet1_rows or not sheet2_rows:
        raise ValueError("Cada hoja necesita al menos una fila.")
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES_2)
        zf.writestr("_rels/.rels", _ROOT_RELS)
        zf.writestr(
            "xl/workbook.xml",
            _workbook_xml_two_sheets(
                sheet1_name, sheet2_name, sheet2_hidden=sheet2_hidden
            ),
        )
        zf.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS_2)
        zf.writestr("xl/worksheets/sheet1.xml", _sheet_xml_from_rows(sheet1_rows))
        zf.writestr("xl/worksheets/sheet2.xml", _sheet_xml_from_rows(sheet2_rows))
        zf.writestr("xl/styles.xml", _STYLES)
    data = buf.getvalue()
    if len(data) < 32:
        raise ValueError("El Excel generado está vacío")
    return data


def evaluacion_plantilla_xlsx_bytes(
    *,
    grupo: str,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
    materia_label: str,
    criterios: list[str],
    alumnos: list[str],
    data_sheet: str = "Calificaciones",
    meta_sheet: str = "_meta",
) -> bytes:
    """Plantilla Evaluar competencias (hoja datos + _meta oculta), solo en RAM."""
    data_rows: list[list[object]] = [["Alumno", *criterios]]
    for alumno in alumnos:
        data_rows.append([alumno, *([""] * len(criterios))])
    meta_rows: list[list[object]] = [
        ["campo", "valor"],
        ["grupo", grupo],
        ["etapa", etapa],
        ["curso", int(curso_asignatura)],
        ["materia_key", materia_key],
        ["materia", materia_label],
        ["criterios", "|".join(criterios)],
    ]
    return two_sheets_xlsx_bytes(
        sheet1_name=data_sheet,
        sheet1_rows=data_rows,
        sheet2_name=meta_sheet,
        sheet2_rows=meta_rows,
        sheet2_hidden=True,
    )
