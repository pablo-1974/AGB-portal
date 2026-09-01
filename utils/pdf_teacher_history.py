# utils/pdf_teacher_history.py
from io import BytesIO
from pathlib import Path
from datetime import date

from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet


def pdf_teacher_history(
    *,
    rows: list[dict],
    titulo: str,
    fecha_desde: date,
    fecha_hasta: date,
    logo_path: Path | None = None,
) -> bytes:
    buf = BytesIO()

    if isinstance(fecha_desde, str):
        fecha_desde = date.fromisoformat(fecha_desde)
    if isinstance(fecha_hasta, str):
        fecha_hasta = date.fromisoformat(fecha_hasta)

    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
    )

    styles = getSampleStyleSheet()
    style_title = styles["Heading2"]
    style_cell = styles["BodyText"]
    style_cell.fontSize = 9
    style_cell.leading = 11
    elements = []

    header_cells = []
    if logo_path and logo_path.exists():
        header_cells.append(Image(str(logo_path), width=60, height=60))
    else:
        header_cells.append("")

    title_txt = (
        f"<b>{titulo}</b><br/>"
        f"<font size=9>"
        f"Periodo: {fecha_desde.strftime('%d/%m/%Y')} – {fecha_hasta.strftime('%d/%m/%Y')}"
        f"</font>"
    )
    header_cells.append(Paragraph(title_txt, style_title))
    header = Table([header_cells], colWidths=[70, doc.width - 70])
    elements.append(header)
    elements.append(Spacer(1, 14))

    headers = ["Nº", "Fecha", "Hora / Franja", "Grupo", "Alumno", "Gravedad", "Descripción"]
    col_widths = [36, 70, 70, 70, 140, 70, 344]

    # Mismo criterio que /incidents/list: orden por fecha descendente (más reciente primero)
    # y numeración 1..N donde 1 es la incidencia más antigua del resultado filtrado.
    total = len(rows)
    data = [[Paragraph(f"<b>{h}</b>", styles["Heading4"]) for h in headers]]
    for idx, r in enumerate(rows):
        num = total - idx
        data.append(
            [
                Paragraph(str(num), style_cell),
                Paragraph(str(r.get("fecha", "") or ""), style_cell),
                Paragraph(str(r.get("hora", "") or ""), style_cell),
                Paragraph(str(r.get("grupo", "") or ""), style_cell),
                Paragraph(str(r.get("alumno", "") or ""), style_cell),
                Paragraph(str(r.get("gravedad", "") or ""), style_cell),
                Paragraph(str(r.get("descripcion", "") or ""), style_cell),
            ]
        )

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(table)

    doc.build(elements)
    return buf.getvalue()
