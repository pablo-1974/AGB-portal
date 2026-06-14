# utils/pdf_excursion.py
from io import BytesIO
from pathlib import Path
from datetime import date

from reportlab.lib.pagesizes import A4
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


def pdf_no_aptos_excursion(
    *,
    rows: list[dict],
    actividad: str,
    fecha_excursion: date,
    fecha_desde: date,
    fecha_hasta: date,
    logo_path: Path | None = None,
) -> bytes:
    """
    Genera PDF de 'No aptos para excursión'.
    """

    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    elems = []

    header_cells = []
    if logo_path and logo_path.exists():
        img = Image(str(logo_path), width=60, height=60)
        header_cells.append(img)
    else:
        header_cells.append("")

    title = Paragraph("<b>No aptos para excursión</b>", styles["Title"])
    header_cells.append(title)

    header_table = Table([header_cells], colWidths=[70, doc.width - 70])
    elems.append(header_table)
    elems.append(Spacer(1, 12))

    meta_txt = (
        f"<b>Actividad:</b> {actividad}<br/>"
        f"<b>Fecha de la excursión:</b> {fecha_excursion.strftime('%d/%m/%Y')}<br/>"
        f"<b>Periodo analizado:</b> "
        f"{fecha_desde.strftime('%d/%m/%Y')} – {fecha_hasta.strftime('%d/%m/%Y')}"
    )
    elems.append(Paragraph(meta_txt, styles["BodyText"]))
    elems.append(Spacer(1, 16))

    data = [
        [
            Paragraph("<b>Nº</b>", styles["Heading4"]),
            Paragraph("<b>Grupo</b>", styles["Heading4"]),
            Paragraph("<b>Alumno</b>", styles["Heading4"]),
            Paragraph("<b>Faltas graves / muy graves<br/>(30 días)</b>", styles["Heading4"]),
            Paragraph("<b>Faltas totales</b>", styles["Heading4"]),
        ]
    ]

    for i, r in enumerate(rows, start=1):
        data.append([str(i), r["grupo"], r["alumno"], str(r["graves"]), str(r["total"])])

    table = Table(
        data,
        colWidths=[36, 90, 200, 120, 90],
        repeatRows=1,
    )

    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.75, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
            ]
        )
    )

    elems.append(table)

    doc.build(elems)
    return buf.getvalue()
