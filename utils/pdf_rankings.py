# utils/pdf_rankings.py

from io import BytesIO
from pathlib import Path
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors


def pdf_rankings(
    *,
    rows: list[dict],
    titulo: str,
    columna: str,
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
        pagesize=A4,
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
    )

    styles = getSampleStyleSheet()
    style_title = styles["Heading2"]
    style_cell = styles["BodyText"]
    style_cell.fontSize = 10
    style_cell.leading = 12
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

    if columna == "Alumno":
        data = [[
            Paragraph("<b>#</b>", styles["Heading4"]),
            Paragraph("<b>Alumno</b>", styles["Heading4"]),
            Paragraph("<b>Grupo</b>", styles["Heading4"]),
            Paragraph("<b>Incidencias</b>", styles["Heading4"]),
        ]]
    else:
        data = [[
            Paragraph("<b>#</b>", styles["Heading4"]),
            Paragraph(f"<b>{columna}</b>", styles["Heading4"]),
            Paragraph("<b>Incidencias</b>", styles["Heading4"]),
        ]]

    for i, r in enumerate(rows, start=1):
        if columna == "Alumno":
            data.append(
                [
                    Paragraph(str(i), style_cell),
                    Paragraph(str(r["nombre"]), style_cell),
                    Paragraph(str(r["grupo"]), style_cell),
                    Paragraph(str(r["total"]), style_cell),
                ]
            )
        else:
            data.append(
                [
                    Paragraph(str(i), style_cell),
                    Paragraph(str(r["nombre"]), style_cell),
                    Paragraph(str(r["total"]), style_cell),
                ]
            )

    colWidths = [40, 200, 120, 80] if columna == "Alumno" else [50, 350, doc.width - 400]
    table = Table(data, colWidths=colWidths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (2, 1), (2, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    elements.append(table)
    doc.build(elements)
    return buf.getvalue()
