"""PDF de autorización parental para actividades extraescolares (plantilla en blanco)."""

from __future__ import annotations

import uuid
from pathlib import Path

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from config import settings
from context import institution_display_name
from utils.pdf_markup import pdf_markup


def _portal_static_logo_path() -> Path | None:
    p = settings.BASE_DIR / "static" / "logo.png"
    return p if p.is_file() else None


def _blank(n: int) -> str:
    return "_" * n


def _coste_display(*, gratuita: bool, importe: str) -> str:
    if gratuita:
        return "gratuita"
    imp = (importe or "").strip()
    return imp if imp else "—"


def _draw_page_footer(footer_text: str):
    """Pinta el pie fijo al margen inferior de cada página."""
    bottom_y = 14 * mm

    def _draw(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 10)
        page_w, _ = A4
        canvas.drawCentredString(page_w / 2.0, bottom_y, footer_text)
        canvas.restoreState()

    return _draw


def build_autorizacion_pdf(path: str, data: dict) -> None:
    """Genera el PDF en ``path`` con datos de actividad y huecos para la familia."""
    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=18 * mm,
        bottomMargin=28 * mm,
    )

    styles = getSampleStyleSheet()
    uid = uuid.uuid4().hex[:8]
    style_title = ParagraphStyle(
        name=f"AutTitle_{uid}",
        parent=styles["Heading2"],
        alignment=TA_CENTER,
        fontSize=13,
        leading=16,
        spaceAfter=10,
        fontName="Helvetica-Bold",
    )
    style_body = ParagraphStyle(
        name=f"AutBody_{uid}",
        parent=styles["Normal"],
        alignment=TA_JUSTIFY,
        fontSize=10.5,
        leading=14,
        spaceAfter=4,
    )
    style_apart = ParagraphStyle(
        name=f"AutApart_{uid}",
        parent=style_body,
        firstLineIndent=12,
        spaceBefore=10,
        spaceAfter=10,
    )
    style_block = ParagraphStyle(
        name=f"AutBlock_{uid}",
        parent=style_body,
        leftIndent=12,
        firstLineIndent=0,
        spaceBefore=4,
        spaceAfter=4,
    )
    style_sig = ParagraphStyle(
        name=f"AutSig_{uid}",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=14,
        firstLineIndent=12,
        spaceBefore=10,
        spaceAfter=6,
    )

    flow: list = []

    logo_path = _portal_static_logo_path()
    logo_cell = ""
    if logo_path:
        logo_cell = Image(str(logo_path), width=22 * mm, height=22 * mm)

    header = Table([[logo_cell, ""]], colWidths=[26 * mm, doc.width - 26 * mm])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    flow.append(header)
    flow.append(Spacer(1, 6))
    flow.append(Paragraph("AUTORIZACIÓN PARA ACTIVIDAD EXTRAESCOLAR", style_title))
    flow.append(Spacer(1, 4))

    centro = pdf_markup(
        data.get("centro_nombre")
        or institution_display_name(settings.INSTITUTION_NAME)
    )
    actividad = pdf_markup(data.get("actividad_nombre") or "")
    fecha = pdf_markup(data.get("actividad_fecha_display") or "")
    lugar = pdf_markup(data.get("actividad_lugar") or "")
    hora_desde = pdf_markup(data.get("hora_desde") or "")
    hora_hasta = pdf_markup(data.get("hora_hasta") or "")
    caracteristicas = pdf_markup(data.get("caracteristicas") or "")
    coste = pdf_markup(
        _coste_display(
            gratuita=bool(data.get("coste_gratuita")),
            importe=str(data.get("coste_importe") or ""),
        )
    )
    entregar_a = (data.get("entregar_a") or "").strip().upper()
    footer_line = f"ENTREGAR EN EL CENTRO A {entregar_a}"

    p_ident = (
        f"D./Dª {_blank(38)}, con DNI nº {_blank(18)}, "
        f"padre/madre/tutor legal del alumno/a {_blank(38)}, matriculado/a en el grupo "
        f"{_blank(11)} del centro <b>{centro}</b>."
    )
    flow.append(Paragraph(p_ident, style_body))

    p_autorizo = (
        f"<b>AUTORIZO</b> a mi hijo/a a participar en la actividad extraescolar denominada "
        f"<b>{actividad}</b>, que se llevará a cabo el día <b>{fecha}</b> en <b>{lugar}</b> "
        f"en horario de <b>{hora_desde}</b> a <b>{hora_hasta}</b>."
    )
    flow.append(Paragraph(p_autorizo, style_apart))

    flow.append(
        Paragraph(
            "Declaro haber sido informado/a de las características de la actividad:",
            style_apart,
        )
    )
    flow.append(Paragraph(f"<b>{caracteristicas}</b>", style_block))
    flow.append(
        Paragraph("y doy mi consentimiento para su participación.", style_block)
    )

    if bool(data.get("coste_gratuita")):
        coste_txt = "Coste de la actividad: <b>gratuita</b>."
    else:
        coste_txt = f"Coste de la actividad: <b>{coste}</b> €."
    flow.append(Paragraph(coste_txt, style_apart))
    if not bool(data.get("coste_gratuita")):
        flow.append(
            Paragraph(
                "Asimismo, acepto que, en caso de que el alumno/a sea sancionado/a con la no "
                "asistencia a la actividad por incidencias de comportamiento, el importe abonado "
                "no será reembolsado.",
                style_apart,
            )
        )

    p3 = (
        "Del mismo modo, acepto que, durante el desarrollo de la actividad, el profesorado "
        "responsable adopte las medidas disciplinarias o educativas que considere oportunas en "
        "caso de comportamiento inadecuado del alumno/a, conforme a las normas del centro."
    )
    flow.append(Paragraph(p3, style_apart))

    p4 = (
        "Igualmente, autorizo al profesorado responsable a tomar las decisiones que consideren "
        "oportunas en caso de urgencia médica, intentando siempre contactar previamente conmigo."
    )
    flow.append(Paragraph(p4, style_apart))

    flow.append(Paragraph(f"Teléfono de contacto: {_blank(25)}.", style_apart))
    flow.append(
        Paragraph(
            f"En {_blank(22)}, a {_blank(4)} de {_blank(13)} de {_blank(4)}.",
            style_apart,
        )
    )

    flow.append(Spacer(1, 12))
    flow.append(Paragraph("Firma del padre/madre/tutor legal:", style_sig))

    draw_footer = _draw_page_footer(footer_line)
    doc.build(flow, onFirstPage=draw_footer, onLaterPages=draw_footer)


def autorizacion_pdf_bytes(data: dict) -> bytes:
    import tempfile

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    path = tmp.name
    tmp.close()
    try:
        build_autorizacion_pdf(path, data)
        return Path(path).read_bytes()
    finally:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
