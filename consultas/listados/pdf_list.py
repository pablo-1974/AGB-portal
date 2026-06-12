"""PDF de tablas simples (listados de profesorado, etc.)."""

from __future__ import annotations

import io
import time
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import settings
from utils.pdf_generated_footer import pdf_generated_footer_text


def pdf_markup(value: object) -> str:
    return escape(str(value if value is not None else ""))


def _portal_static_logo_path() -> str | None:
    p = settings.BASE_DIR / "static" / "logo.png"
    return str(p) if p.is_file() else None


def _build_simple_table_flow(
    *,
    center_name: str,
    headline: str,
    headers: list[str],
    rows: list[list[str]],
    styles,
    uid: str,
) -> tuple[list, float]:
    from reportlab.platypus import Image

    style_title = ParagraphStyle(
        name=f"ListTitle_{uid}",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=15,
        leading=18,
    )
    style_center_small = ParagraphStyle(
        name=f"ListCenterSmall_{uid}",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
    )
    style_cell = ParagraphStyle(
        name=f"ListCell_{uid}",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
    )
    style_hdr = ParagraphStyle(
        name=f"ListHdr_{uid}",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        fontName="Helvetica-Bold",
    )
    style_footer = ParagraphStyle(
        name=f"ListFooter_{uid}",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
        textColor=colors.grey,
        fontName="Helvetica-Oblique",
    )

    flow: list = []
    logo = None
    lp = _portal_static_logo_path()
    if lp:
        try:
            logo = Image(lp, width=20 * mm, height=20 * mm)
        except OSError:
            logo = None
    if logo is None:
        logo = Spacer(20 * mm, 1 * mm)

    text_block = [
        Paragraph(pdf_markup((center_name or "").strip() or "IES"), style_center_small),
        Spacer(1, 2),
        Paragraph(pdf_markup((headline or "Listado").strip()), style_title),
    ]
    page_w, _ = A4
    usable_w = page_w - (28 * mm)
    header_table = Table([[logo, text_block]], colWidths=[24 * mm, max(usable_w - 24 * mm, 40 * mm)])
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    flow.append(header_table)
    flow.append(Spacer(1, 8))

    header_cells = [Paragraph(pdf_markup(h), style_hdr) for h in headers]
    body_rows = [[Paragraph(pdf_markup(c), style_cell) for c in row] for row in rows]
    if not body_rows:
        body_rows = [[Paragraph("—", style_cell) for _ in headers]]
    data: list[list] = [header_cells] + body_rows

    col_w = usable_w / len(headers)
    table = Table(data, colWidths=[col_w] * len(headers), repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    flow.append(table)
    flow.append(Spacer(1, 12))
    flow.append(Paragraph(pdf_markup(pdf_generated_footer_text()), style_footer))
    return flow, usable_w


def generate_multi_simple_table_pdf_bytes(
    *,
    center_name: str,
    sections: list[tuple[str, list[str], list[list[str]]]],
) -> bytes:
    if not sections:
        raise ValueError("sections vacío")
    styles = getSampleStyleSheet()
    base_uid = str(int(time.time() * 1000))
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
    )
    flow: list = []
    for i, (headline, headers, rows) in enumerate(sections):
        if not headers:
            continue
        if i > 0:
            flow.append(PageBreak())
        section_flow, _ = _build_simple_table_flow(
            center_name=center_name,
            headline=headline,
            headers=headers,
            rows=rows,
            styles=styles,
            uid=f"{base_uid}_{i}",
        )
        flow.extend(section_flow)
    if not flow:
        raise ValueError("No hay secciones para el PDF")
    doc.build(flow)
    data = buffer.getvalue()
    if len(data) < 32:
        raise ValueError("El PDF generado está vacío")
    return data


def generate_simple_table_pdf_bytes(
    *,
    center_name: str,
    headline: str,
    headers: list[str],
    rows: list[list[str]],
) -> bytes:
    if not headers:
        raise ValueError("La tabla PDF necesita al menos una columna de encabezado.")

    styles = getSampleStyleSheet()
    uid = str(int(time.time() * 1000))
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=14 * mm,
    )
    flow, _ = _build_simple_table_flow(
        center_name=center_name,
        headline=headline,
        headers=headers,
        rows=rows,
        styles=styles,
        uid=uid,
    )
    doc.build(flow)
    data = buffer.getvalue()
    if len(data) < 32:
        raise ValueError("El PDF generado está vacío")
    return data


def generate_simple_table_pdf(
    path_out: str,
    *,
    center_name: str,
    headline: str,
    headers: list[str],
    rows: list[list[str]],
) -> None:
    from pathlib import Path

    Path(path_out).write_bytes(
        generate_simple_table_pdf_bytes(
            center_name=center_name,
            headline=headline,
            headers=headers,
            rows=rows,
        )
    )
