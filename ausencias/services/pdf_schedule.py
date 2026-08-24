# services/pdf_schedule.py
import io
import re

from config import settings
from utils.pdf_generated_footer import pdf_generated_footer_text


def _sanitize_pdf_title_line(title_line: str) -> str:
    """Quita prefijos legados «Horario semanal …» del título del PDF."""
    t = (title_line or "").strip()
    if not t:
        return t
    m = re.match(r"^Horario\s+semanal\s*[\u2014\u2013\-–:]?\s*", t, re.IGNORECASE)
    if m:
        t = t[m.end() :].strip()
    return t or (title_line or "").strip()


def _reportlab():
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import (
        SimpleDocTemplate,
        Table,
        TableStyle,
        Paragraph,
        Spacer,
        Image,
        PageBreak,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib import colors
    from reportlab.lib.units import mm

    return {
        "A4": A4,
        "SimpleDocTemplate": SimpleDocTemplate,
        "Table": Table,
        "TableStyle": TableStyle,
        "Paragraph": Paragraph,
        "Spacer": Spacer,
        "Image": Image,
        "PageBreak": PageBreak,
        "getSampleStyleSheet": getSampleStyleSheet,
        "ParagraphStyle": ParagraphStyle,
        "TA_CENTER": TA_CENTER,
        "colors": colors,
        "mm": mm,
    }


def _portal_static_logo_path():
    p = settings.BASE_DIR / "static" / "logo.png"
    return str(p) if p.is_file() else None


def _append_group_staff_table(flow, group_staff: list[dict], doc, rl: dict, styles) -> None:
    """Tabla nombre / asignatura debajo del horario (vista grupos)."""
    if not group_staff:
        return
    Table = rl["Table"]
    TableStyle = rl["TableStyle"]
    Paragraph = rl["Paragraph"]
    Spacer = rl["Spacer"]
    ParagraphStyle = rl["ParagraphStyle"]
    colors = rl["colors"]

    style_section = ParagraphStyle(
        name="GroupStaffTitle",
        parent=styles["Normal"],
        fontSize=11,
        leading=13,
        fontName="Helvetica-Bold",
    )
    style_cell = ParagraphStyle(
        name="GroupStaffCell",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
    )
    style_hdr = ParagraphStyle(
        name="GroupStaffHdr",
        parent=styles["Normal"],
        fontSize=9,
        leading=11,
        fontName="Helvetica-Bold",
    )

    flow.append(Spacer(1, 8))
    flow.append(Paragraph("Profesorado del grupo", style_section))
    flow.append(Spacer(1, 4))

    data = [
        [Paragraph("Nombre", style_hdr), Paragraph("Asignatura", style_hdr)],
    ]
    for row in group_staff:
        data.append(
            [
                Paragraph(str(row.get("nombre") or ""), style_cell),
                Paragraph(str(row.get("asignatura") or ""), style_cell),
            ]
        )

    page_width, _ = rl["A4"]
    usable = page_width - (doc.leftMargin + doc.rightMargin)
    col_widths = [usable * 0.45, usable * 0.55]
    table = Table(data, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    flow.append(table)


def build_schedule_pdf_flowables(
    *,
    center_name: str,
    title_line: str,
    schedule,
    doc,
    rl: dict | None = None,
    guardias_recreo_split_labels: bool = False,
    group_staff: list[dict] | None = None,
):
    if rl is None:
        rl = _reportlab()
    A4 = rl["A4"]
    Table = rl["Table"]
    TableStyle = rl["TableStyle"]
    Paragraph = rl["Paragraph"]
    Spacer = rl["Spacer"]
    Image = rl["Image"]
    getSampleStyleSheet = rl["getSampleStyleSheet"]
    ParagraphStyle = rl["ParagraphStyle"]
    TA_CENTER = rl["TA_CENTER"]
    colors = rl["colors"]
    mm = rl["mm"]

    styles = getSampleStyleSheet()
    style_center = ParagraphStyle(
        name="Center",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=10,
    )
    style_title = ParagraphStyle(
        name="Title",
        parent=styles["Heading1"],
        alignment=TA_CENTER,
        fontSize=16,
        leading=20,
    )
    style_center_small = ParagraphStyle(
        name="CenterSmall",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
    )
    style_cell = ParagraphStyle(
        name="Cell",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=8,
        leading=9,
    )

    days = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
    franjas = ["1ª", "2ª", "3ª", "Recreo", "4ª", "5ª", "6ª"]

    flow = []

    logo = None
    logo_path = _portal_static_logo_path()
    if logo_path:
        try:
            logo = Image(logo_path, width=22 * mm, height=22 * mm)
        except OSError:
            logo = None
    if logo is None:
        logo = Spacer(22 * mm, 1 * mm)

    title_clean = _sanitize_pdf_title_line(title_line)
    text_block = [
        Paragraph(center_name, style_center_small),
        Spacer(1, 2),
        Paragraph(title_clean, style_title),
    ]

    header_table = Table([[logo, text_block]], colWidths=[26 * mm, None])
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
    flow.append(Spacer(1, 6))

    data = [["Hora"] + days]
    page_width, _page_height = A4
    usable = page_width - (doc.leftMargin + doc.rightMargin)
    col0 = 21 * mm
    col_other = (usable - col0) / 5
    col_widths = [col0] + [col_other] * 5

    row_heights = [12 * mm]
    for fr in franjas:
        if fr == "Recreo" and guardias_recreo_split_labels:
            row_heights.append(16 * mm)
        else:
            row_heights.append(9 * mm if fr == "Recreo" else 17 * mm)

    for i, fr in enumerate(franjas):
        row_label = "G PASILLO<br/>G PATIO" if (fr == "Recreo" and guardias_recreo_split_labels) else fr
        row = [row_label]
        for d in range(5):
            item = schedule[i][d]
            if item is None:
                row.append("")
            elif item["type"] == "CLASS":
                g = (item.get("group") or "").strip()
                rm = (item.get("room") or "").strip()
                subj = (item.get("subject") or "").strip()
                parts = [p for p in (g, rm, subj) if p]
                txt = "<br/>".join(parts) if parts else ""
                row.append(Paragraph(txt, style_cell) if txt else "")
            elif item["type"] == "GUARD":
                txt = f"{item['guard_type']}"
                row.append(Paragraph(txt, style_cell))
            elif item["type"] == "OTHER":
                txt = (item.get("subject") or "").strip() or "Otros"
                row.append(Paragraph(txt, style_cell))
            else:
                row.append("")
        data.append(row)

    data[0] = [Paragraph(str(x), style_center) for x in data[0]]
    for i in range(1, len(data)):
        data[i][0] = Paragraph(str(data[i][0]), style_center)

    table = Table(data, colWidths=col_widths, rowHeights=row_heights, repeatRows=1)
    table_style = TableStyle(
        [
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("BACKGROUND", (0, 1), (0, -1), colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
    )
    recreo_row = 1 + franjas.index("Recreo")
    table_style.add("BACKGROUND", (0, recreo_row), (-1, recreo_row), colors.whitesmoke)
    table_style.add("TEXTCOLOR", (1, recreo_row), (-1, recreo_row), colors.darkmagenta)
    table.setStyle(table_style)

    flow.append(table)
    if group_staff:
        _append_group_staff_table(flow, group_staff, doc, rl, styles)
    flow.append(Spacer(1, 10))
    style_footer = ParagraphStyle(
        name="PdfSchedFooter",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
        textColor=colors.grey,
        fontName="Helvetica-Oblique",
    )
    flow.append(Paragraph(pdf_generated_footer_text(), style_footer))
    return flow


def generate_schedule_pdf_with_title_bytes(
    center_name: str,
    headline: str,
    schedule,
    *,
    guardias_recreo_split_labels: bool = False,
    group_staff: list[dict] | None = None,
) -> bytes:
    rl = _reportlab()
    A4 = rl["A4"]
    SimpleDocTemplate = rl["SimpleDocTemplate"]
    mm = rl["mm"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    flow = build_schedule_pdf_flowables(
        center_name=center_name,
        title_line=headline,
        schedule=schedule,
        doc=doc,
        rl=rl,
        guardias_recreo_split_labels=guardias_recreo_split_labels,
        group_staff=group_staff,
    )
    doc.build(flow)
    data = buffer.getvalue()
    if len(data) < 32:
        raise ValueError("PDF de horario vacío")
    return data


def generate_schedule_pdf_with_title(
    path_out: str,
    center_name: str,
    headline: str,
    schedule,
    *,
    guardias_recreo_split_labels: bool = False,
    group_staff: list[dict] | None = None,
) -> None:
    from pathlib import Path

    Path(path_out).write_bytes(
        generate_schedule_pdf_with_title_bytes(
            center_name,
            headline,
            schedule,
            guardias_recreo_split_labels=guardias_recreo_split_labels,
            group_staff=group_staff,
        )
    )


def generate_schedule_pdf(path, teacher_name, center_name, schedule):
    """schedule = matriz 7×5 de dicts (CLASS / GUARD / OTHER) o ``None``."""
    name = (teacher_name or "").strip() or "Profesor"
    generate_schedule_pdf_with_title(
        path,
        center_name,
        name,
        schedule,
    )


def generate_multi_teacher_schedule_pdf_bytes(
    center_name: str,
    sections: list[tuple[str, list] | tuple[str, list, list[dict] | None]],
) -> bytes:
    if not sections:
        raise ValueError("sections vacío")
    rl = _reportlab()
    A4 = rl["A4"]
    SimpleDocTemplate = rl["SimpleDocTemplate"]
    PageBreak = rl["PageBreak"]
    mm = rl["mm"]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    flow = []
    for i, section in enumerate(sections):
        if len(section) >= 3:
            title_line, sched, group_staff = section[0], section[1], section[2]
        else:
            title_line, sched = section[0], section[1]
            group_staff = None
        if i > 0:
            flow.append(PageBreak())
        flow.extend(
            build_schedule_pdf_flowables(
                center_name=center_name,
                title_line=title_line,
                schedule=sched,
                doc=doc,
                rl=rl,
                group_staff=group_staff,
            )
        )
    doc.build(flow)
    data = buffer.getvalue()
    if len(data) < 32:
        raise ValueError("PDF de horarios vacío")
    return data


def generate_multi_teacher_schedule_pdf(path_out: str, center_name: str, sections: list[tuple[str, list]]) -> None:
    from pathlib import Path

    Path(path_out).write_bytes(
        generate_multi_teacher_schedule_pdf_bytes(center_name, sections)
    )
