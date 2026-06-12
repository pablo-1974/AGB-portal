"""
PDF parte mensual: maquetación como consultas `services/pdf_monthly.build_monthly_report_pdf`.
"""
from __future__ import annotations

import html
import uuid
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ausencias.services.monthly_report import monthly_pdf_title
from ausencias.services.pdf_schedule import _portal_static_logo_path
from config import settings


def _build_monthly_report_elements(
    *,
    date_from: date,
    date_to: date,
    pdf_body_rows: list[list[str]],
) -> list[Any]:
    styles = getSampleStyleSheet()
    uid = uuid.uuid4().hex[:8]
    style_center_small = ParagraphStyle(
        name=f"MonthlyCenterSmall_{uid}",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
    )
    style_title = ParagraphStyle(
        name=f"MonthlyTitle_{uid}",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=16,
        leading=20,
    )

    elements: list[Any] = []

    logo_path = _portal_static_logo_path()
    if logo_path:
        try:
            img = Image(logo_path, width=22 * mm, height=22 * mm)
            img.hAlign = "CENTER"
            elements.append(img)
            elements.append(Spacer(1, 4))
        except OSError:
            pass

    inst = (settings.INSTITUTION_NAME or "").strip()
    if inst:
        elements.append(Paragraph(html.escape(inst), style_center_small))

    elements.append(Paragraph(html.escape(monthly_pdf_title(date_from, date_to)), style_title))
    elements.append(Spacer(1, 10))

    body = pdf_body_rows[:] if pdf_body_rows else [["-", "-", "-", "-", "0"]]
    data = [["NOMBRE", "FECHA", "HORAS", "CAUSA", "DÍAS"]] + body

    table = Table(
        data,
        colWidths=[
            A4[0] * 0.30,
            A4[0] * 0.22,
            A4[0] * 0.15,
            A4[0] * 0.18,
            A4[0] * 0.10,
        ],
    )

    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    elements.append(table)
    return elements


def render_monthly_report_pdf_bytes(
    *,
    date_from: date,
    date_to: date,
    pdf_body_rows: list[list[str]],
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    doc.build(
        _build_monthly_report_elements(
            date_from=date_from,
            date_to=date_to,
            pdf_body_rows=pdf_body_rows,
        )
    )
    data = buffer.getvalue()
    if len(data) < 32:
        raise ValueError("El PDF del parte mensual está vacío")
    return data


def render_monthly_report_pdf_legacy(
    path_out: str,
    *,
    date_from: date,
    date_to: date,
    pdf_body_rows: list[list[str]],
) -> None:
    Path(path_out).write_bytes(
        render_monthly_report_pdf_bytes(
            date_from=date_from,
            date_to=date_to,
            pdf_body_rows=pdf_body_rows,
        )
    )
