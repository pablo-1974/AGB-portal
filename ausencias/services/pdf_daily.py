"""
PDF parte diario: maquetación legacy (consultas `services/pdf_daily.build_daily_report_pdf` OLD3).
"""
from __future__ import annotations

import html
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ausencias.services.daily_report import HOUR_ROWS, RECREO_INDEX
from ausencias.services.pdf_schedule import _portal_static_logo_path

_COMIC_SANS_RL_NAME = "ComicSansMS"


def _comic_sans_font_path() -> Path | None:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidates = (
        Path(windir) / "Fonts" / "comic.ttf",
        Path(windir) / "Fonts" / "comicbd.ttf",
        Path("/usr/share/fonts/truetype/msttcorefonts/Comic_Sans_MS.ttf"),
        Path("/usr/share/fonts/truetype/microsoft-comic-neue/ComicSansMS.ttf"),
        Path("/Library/Fonts/Comic Sans MS.ttf"),
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def _comic_sans_font_name() -> str:
    if _COMIC_SANS_RL_NAME in pdfmetrics.getRegisteredFontNames():
        return _COMIC_SANS_RL_NAME
    path = _comic_sans_font_path()
    if path:
        pdfmetrics.registerFont(TTFont(_COMIC_SANS_RL_NAME, str(path)))
        return _COMIC_SANS_RL_NAME
    return "Helvetica"


def _daily_report_title_style(base_styles, *, uid: str) -> ParagraphStyle:
    return ParagraphStyle(
        name=f"DailyReportPdfTitle_{uid}",
        parent=base_styles["Title"],
        fontName=_comic_sans_font_name(),
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
    )


def _build_daily_report_elements(preview: dict[str, Any]) -> list[Any]:
    """Devuelve los flowables del parte diario."""
    styles = getSampleStyleSheet()
    uid = uuid.uuid4().hex[:8]
    head = preview["head"]
    rows = preview["rows"]
    data = [head] + rows

    total_width = A4[0] - 2.4 * cm

    elements: list[Any] = []

    logo_path = _portal_static_logo_path()
    if logo_path:
        try:
            img = Image(logo_path, width=2.2 * cm, height=2.2 * cm)
            img.hAlign = "CENTER"
            elements.append(img)
            elements.append(Spacer(1, 6))
        except OSError:
            pass

    title_text = html.escape(preview.get("pdf_title") or preview.get("title") or "")
    elements.append(Paragraph(title_text, _daily_report_title_style(styles, uid=uid)))
    elements.append(Spacer(1, 6))

    parts: list[str] = []
    agr = preview.get("ausentes_guardia_recreo") or []
    if agr:
        labels = "; ".join(str(x).strip() for x in agr if str(x).strip())
        if labels:
            parts.append(f"Ausentes Guardia Recreo: {labels}")

    obs_user = (preview.get("observaciones") or "").strip()
    if obs_user:
        parts.append(obs_user)

    obs_plain = "; ".join(parts) if parts else "—"
    obs_safe = html.escape(obs_plain).replace("\n", "<br/>")

    obs_table = Table(
        [[Paragraph(f"<b>Observaciones:</b><br/>{obs_safe}", styles["Normal"])]],
        colWidths=[total_width],
        rowHeights=[72],
    )
    obs_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    elements.append(obs_table)
    elements.append(Spacer(1, 8))

    col_widths = [
        1.0 * cm,
        total_width * 0.32,
        total_width * 0.10,
        total_width * 0.10,
        total_width * 0.10,
        total_width * 0.18,
        total_width * 0.20,
    ]

    row_h = 82
    recreo_h = 44
    row_heights = [16] + [
        (recreo_h if idx == RECREO_INDEX else row_h) for idx in range(len(HOUR_ROWS))
    ]

    table = Table(data, colWidths=col_widths, rowHeights=row_heights)

    ts = TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]
    )

    recreo_row_index = 1 + RECREO_INDEX
    ts.add("SPAN", (0, recreo_row_index), (-1, recreo_row_index))
    ts.add("ALIGN", (0, recreo_row_index), (-1, recreo_row_index), "CENTER")
    ts.add("VALIGN", (0, recreo_row_index), (-1, recreo_row_index), "MIDDLE")
    ts.add("FONTSIZE", (0, recreo_row_index), (-1, recreo_row_index), 12)

    table.setStyle(ts)
    elements.append(table)
    return elements


def render_daily_report_pdf_bytes(preview: dict[str, Any]) -> bytes:
    """
    Genera el PDF del parte diario en memoria.
    ``preview`` debe incluir ``pdf_title``, ``observaciones``, ``ausentes_guardia_recreo``,
    ``head``, ``rows`` (como ``build_daily_report_preview``).
    """
    elements = _build_daily_report_elements(preview)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.2 * cm,
        rightMargin=1.2 * cm,
        topMargin=1.0 * cm,
        bottomMargin=1.0 * cm,
    )
    doc.build(elements)
    data = buffer.getvalue()
    if len(data) < 32:
        raise ValueError("El PDF del parte diario está vacío")
    return data


def render_daily_report_pdf_legacy(path_out: str, preview: dict[str, Any]) -> None:
    """
    Escribe el PDF del parte diario en ``path_out``.
    ``preview`` debe incluir ``pdf_title``, ``observaciones``, ``ausentes_guardia_recreo``,
    ``head``, ``rows`` (como ``build_daily_report_preview``).
    """
    Path(path_out).write_bytes(render_daily_report_pdf_bytes(preview))
