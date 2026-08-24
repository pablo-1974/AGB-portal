"""PDF de tablas simples (listados de profesorado, etc.)."""

from __future__ import annotations

import io
import time
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

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


class _VerticalText(Flowable):
    """Texto rotado 90° para cabeceras de asignaturas."""

    def __init__(self, text: str, *, font_size: float = 6.5, height: float = 48):
        Flowable.__init__(self)
        self.text = (text or "")[:36]
        self.font_size = font_size
        self._height = height
        self._width = max(font_size + 2, 4)

    def wrap(self, availWidth, availHeight):
        return (self._width, self._height)

    def draw(self):
        self.canv.saveState()
        self.canv.setFont("Helvetica", self.font_size)
        self.canv.translate(self._width - 1, 5)
        self.canv.rotate(90)
        self.canv.drawString(0, 0, self.text)
        self.canv.restoreState()


def generate_matricula_matrix_pdf_bytes(
    *,
    center_name: str,
    headline: str,
    alumnos: list[str] | None = None,
    alumno_rows: list[dict[str, str]] | None = None,
    materias: list[str],
    enrolled: set[tuple[str, str]],
) -> bytes:
    """
    PDF matriz: filas = alumnos, columnas = asignaturas, última = total matriculadas.
    Blanco = matriculado; oscuro = no matriculado.

    Tipografía fija. Ancho preferido por asignatura fijo; solo se estrecha
    si no caben todas las columnas en la página.
    """
    from reportlab.platypus import Image
    from reportlab.pdfbase.pdfmetrics import stringWidth

    rows_in: list[dict[str, str]] = []
    if alumno_rows:
        for r in alumno_rows:
            label = str(r.get("label") or "").strip()
            key = str(r.get("key") or "").strip() or label
            if label:
                rows_in.append({"key": key, "label": label})
    elif alumnos:
        for a in alumnos:
            label = str(a or "").strip()
            if not label:
                continue
            a_raw = " ".join(label.split()).replace(" ,", ",").replace(", ", ",")
            key = " ".join(a_raw.replace(",", ", ").split()).casefold()
            rows_in.append({"key": key, "label": label})

    if not rows_in:
        raise ValueError("No hay alumnos para la tabla")
    if not materias:
        raise ValueError("No hay asignaturas para la tabla")

    styles = getSampleStyleSheet()
    uid = str(int(time.time() * 1000))
    page_w, _page_h = landscape(A4)
    left_m = right_m = 10 * mm
    top_m = 10 * mm
    bottom_m = 12 * mm
    usable_w = page_w - left_m - right_m

    style_title = ParagraphStyle(
        name=f"MatTitle_{uid}",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=13,
        leading=16,
    )
    style_center_small = ParagraphStyle(
        name=f"MatCenter_{uid}",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=8,
    )
    style_name = ParagraphStyle(
        name=f"MatName_{uid}",
        parent=styles["Normal"],
        fontSize=7,
        leading=8.5,
    )
    style_total = ParagraphStyle(
        name=f"MatTotal_{uid}",
        parent=styles["Normal"],
        fontSize=7,
        leading=8.5,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
    )
    style_footer = ParagraphStyle(
        name=f"MatFooter_{uid}",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=8,
        textColor=colors.grey,
        fontName="Helvetica-Oblique",
    )
    style_legend = ParagraphStyle(
        name=f"MatLegend_{uid}",
        parent=styles["Normal"],
        fontSize=7.5,
        textColor=colors.Color(0.25, 0.25, 0.25),
    )

    flow: list = []
    logo = None
    lp = _portal_static_logo_path()
    if lp:
        try:
            logo = Image(lp, width=16 * mm, height=16 * mm)
        except OSError:
            logo = None
    if logo is None:
        logo = Spacer(16 * mm, 1 * mm)

    text_block = [
        Paragraph(pdf_markup((center_name or "").strip() or "IES"), style_center_small),
        Spacer(1, 1),
        Paragraph(pdf_markup((headline or "Tabla de matrícula").strip()), style_title),
    ]
    header_table = Table(
        [[logo, text_block]],
        colWidths=[20 * mm, max(usable_w - 20 * mm, 40 * mm)],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    flow.append(header_table)
    flow.append(Spacer(1, 6))
    flow.append(
        Paragraph(
            "Casilla en blanco = asignatura matriculada · Casilla oscura = no matriculada",
            style_legend,
        )
    )
    flow.append(Spacer(1, 4))

    labels = [r["label"] for r in rows_in]
    name_col_w = min(
        58 * mm,
        max(
            28 * mm,
            max((stringWidth(a, "Helvetica", 7) for a in labels), default=40) + 8,
        ),
    )
    total_col_w = 12 * mm
    n_mat = len(materias)
    # Tipografía fija. Ancho preferido por asignatura = 4 mm; solo se reduce
    # si con ese ancho no caben todas en la página.
    preferred_mat_col_w = 4 * mm
    avail_for_mat = max(0.0, usable_w - name_col_w - total_col_w)
    if n_mat * preferred_mat_col_w <= avail_for_mat:
        mat_col_w = preferred_mat_col_w
    else:
        mat_col_w = max(2.0 * mm, avail_for_mat / n_mat)

    header_font = 6.5
    max_label_w = max(
        (stringWidth((m or "")[:36], "Helvetica", header_font) for m in materias),
        default=40,
    )
    header_h = min(95, max(48, max_label_w + 14))

    header_row: list = [
        Paragraph("<b>Alumno</b>", style_name),
        *[_VerticalText(m, font_size=header_font, height=header_h) for m in materias],
        Paragraph("<b>Total</b>", style_total),
    ]
    data: list[list] = [header_row]
    style_cmds: list = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.88, 0.88, 0.88)),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("LEFTPADDING", (0, 0), (0, -1), 3),
        ("RIGHTPADDING", (0, 0), (0, -1), 3),
        ("LEFTPADDING", (1, 0), (-1, -1), 1),
        ("RIGHTPADDING", (1, 0), (-1, -1), 1),
        ("BACKGROUND", (-1, 0), (-1, -1), colors.Color(0.93, 0.93, 0.93)),
    ]
    dark = colors.Color(0.32, 0.32, 0.32)

    for i, row_info in enumerate(rows_in):
        row_idx = i + 1
        a_key = row_info["key"]
        total = 0
        row: list = [Paragraph(pdf_markup(row_info["label"]), style_name)]
        for j, materia in enumerate(materias):
            is_enrolled = (a_key, materia.casefold()) in enrolled
            if is_enrolled:
                total += 1
            else:
                style_cmds.append(
                    ("BACKGROUND", (j + 1, row_idx), (j + 1, row_idx), dark)
                )
            row.append("")
        row.append(Paragraph(str(total), style_total))
        data.append(row)

    col_widths = [name_col_w] + [mat_col_w] * n_mat + [total_col_w]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle(style_cmds))
    flow.append(table)
    flow.append(Spacer(1, 10))
    flow.append(Paragraph(pdf_markup(pdf_generated_footer_text()), style_footer))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=left_m,
        rightMargin=right_m,
        topMargin=top_m,
        bottomMargin=bottom_m,
    )
    doc.build(flow)
    out = buffer.getvalue()
    if len(out) < 32:
        raise ValueError("El PDF generado está vacío")
    return out
