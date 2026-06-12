"""PDF con resumen de actividad extraescolar y listado de alumnado."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import settings
from context import institution_display_name
from extraescolares.calendar_view import format_date_es
from utils.pdf_generated_footer import pdf_generated_footer_text
from utils.pdf_markup import pdf_markup


def _portal_static_logo_path() -> Path | None:
    p = settings.BASE_DIR / "static" / "logo.png"
    return p if p.is_file() else None


def build_actividad_resumen_pdf(path: str, act: dict) -> None:
    """Genera PDF con resumen y tabla de alumnado inscrito."""
    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        name="ActResTitle",
        parent=styles["Heading2"],
        alignment=TA_CENTER,
        fontSize=14,
        leading=17,
        spaceAfter=8,
        fontName="Helvetica-Bold",
    )
    style_center = ParagraphStyle(
        name="ActResCenter",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
        leading=11,
    )
    style_label = ParagraphStyle(
        name="ActResLabel",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        fontName="Helvetica-Bold",
        textColor=colors.grey,
    )
    style_value = ParagraphStyle(
        name="ActResValue",
        parent=styles["Normal"],
        fontSize=10,
        leading=13,
    )
    style_section = ParagraphStyle(
        name="ActResSection",
        parent=styles["Normal"],
        fontSize=11,
        leading=14,
        fontName="Helvetica-Bold",
        spaceBefore=10,
        spaceAfter=6,
    )
    style_cell = ParagraphStyle(
        name="ActResCell",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
    )
    style_hdr = ParagraphStyle(
        name="ActResHdr",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        fontName="Helvetica-Bold",
    )
    style_footer = ParagraphStyle(
        name="ActResFooter",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=8,
        textColor=colors.grey,
        fontName="Helvetica-Oblique",
        spaceBefore=10,
    )

    flow: list = []
    center = institution_display_name(settings.INSTITUTION_NAME)
    actividad = (act.get("actividad") or "").strip()
    fecha = format_date_es(act["fecha"]) if act.get("fecha") else "—"

    logo_path = _portal_static_logo_path()
    logo_cell: object = ""
    if logo_path:
        logo_cell = Image(str(logo_path), width=20 * mm, height=20 * mm)

    header = Table(
        [[logo_cell, Paragraph(pdf_markup(center), style_center)]],
        colWidths=[24 * mm, doc.width - 24 * mm],
    )
    header.setStyle(
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
    flow.append(header)
    flow.append(Spacer(1, 6))
    flow.append(Paragraph(pdf_markup(actividad or "Actividad extraescolar"), style_title))
    flow.append(Spacer(1, 4))

    summary_rows = [
        ("Fecha", fecha),
        ("Lugar", (act.get("lugar") or "").strip() or "—"),
        ("Departamento", (act.get("departamento") or "").strip() or "—"),
        ("Horas de ausencia", (act.get("hours_display") or "—")),
        ("Responsable", (act.get("responsable_name") or "").strip() or "—"),
        ("Acompañantes", (act.get("acompanantes_names") or "").strip() or "—"),
        ("Estado", (act.get("status_label") or "—")),
        (
            "Alumnado",
            f"{int(act.get('total_alumnos') or 0)} inscrito(s)"
            f" · {int(act.get('confirmados') or 0)} confirmado(s)",
        ),
    ]

    half_w = doc.width / 2
    label_w = 26 * mm
    value_w = half_w - label_w - 2 * mm
    col_widths = [label_w, value_w, label_w, value_w]

    left_rows = summary_rows[:4]
    right_rows = summary_rows[4:]
    summary_data: list[list] = []
    for i in range(max(len(left_rows), len(right_rows))):
        row: list = []
        for pairs, idx in ((left_rows, i), (right_rows, i)):
            if idx < len(pairs):
                label, value = pairs[idx]
                row.append(Paragraph(pdf_markup(label), style_label))
                row.append(Paragraph(pdf_markup(value), style_value))
            else:
                row.extend(["", ""])
        summary_data.append(row)

    summary_table = Table(summary_data, colWidths=col_widths)
    summary_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (1, -1), 6),
                ("RIGHTPADDING", (2, 0), (2, -1), 0),
                ("RIGHTPADDING", (3, 0), (3, -1), 4),
            ]
        )
    )
    flow.append(summary_table)

    flow.append(Paragraph("Alumnado inscrito", style_section))

    students = act.get("students") or []
    table_data: list[list] = [
        [
            Paragraph("Grupo", style_hdr),
            Paragraph("Alumno/a", style_hdr),
        ]
    ]
    if students:
        for s in students:
            table_data.append(
                [
                    Paragraph(pdf_markup(s.get("grupo") or "—"), style_cell),
                    Paragraph(pdf_markup(s.get("alumno") or "—"), style_cell),
                ]
            )
    else:
        table_data.append(
            [
                Paragraph("—", style_cell),
                Paragraph("Sin alumnado inscrito", style_cell),
            ]
        )

    student_table = Table(table_data, colWidths=[doc.width * 0.22, doc.width * 0.78])
    student_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    flow.append(student_table)
    flow.append(Spacer(1, 8))
    flow.append(Paragraph(pdf_markup(pdf_generated_footer_text()), style_footer))

    doc.build(flow)
