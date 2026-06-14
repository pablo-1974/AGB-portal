"""Exportación DOCX mínima en memoria (stdlib, sin python-docx)."""

from __future__ import annotations

import zipfile
from io import BytesIO
from xml.sax.saxutils import escape


def _esc(text: object) -> str:
    return escape("" if text is None else str(text))


def _cell(text: object) -> str:
    t = _esc(text)
    return f"<w:tc><w:p><w:r><w:t xml:space=\"preserve\">{t}</w:t></w:r></w:p></w:tc>"


def _row(cells: list[object]) -> str:
    return "<w:tr>" + "".join(_cell(c) for c in cells) + "</w:tr>"


def simple_table_docx_bytes(
    *,
    title: str,
    headers: list[str],
    rows: list[list[object]],
) -> bytes:
    if not headers:
        raise ValueError("La tabla Word necesita al menos un encabezado.")

    title_xml = (
        f'<w:p><w:r><w:rPr><w:b/></w:rPr>'
        f'<w:t xml:space="preserve">{_esc(title)}</w:t></w:r></w:p>'
    )
    table_xml = "<w:tbl>" + _row(headers) + "".join(_row(r) for r in rows) + "</w:tbl>"
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{title_xml}{table_xml}</w:body></w:document>"
    )

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("word/document.xml", document_xml)

    data = buf.getvalue()
    if len(data) < 32:
        raise ValueError("El documento Word generado está vacío")
    return data
