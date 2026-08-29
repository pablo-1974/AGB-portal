# utils/pdf_incident_ticket.py

from io import BytesIO
from datetime import datetime, date

from utils.time_madrid import now_madrid

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


def incident_ticket_pdf(
    alumno: str,
    fecha: date,
    hora: str,
    profesor: str,
    descripcion: str,
    gravedad_inicial: str,
    gravedad_final: str | None,
    enviado_por: str,
    enviado_dt: datetime | None = None,
) -> bytes:
    """
    Genera un PDF tipo 'parte' individual de incidencias.
    Incluye gravedad inicial y final (si existe).
    """

    if enviado_dt is None:
        enviado_dt = now_madrid()

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
    st_title = styles["Title"]
    st_body = styles["BodyText"]
    st_body.fontSize = 11
    st_body.leading = 14

    elems = []

    elems.append(
        Paragraph(
            "Parte de Incidencias. IES Antonio García Bellido.",
            st_title,
        )
    )
    elems.append(Spacer(1, 12))

    f_str = (
        fecha.strftime("%d/%m/%Y")
        if isinstance(fecha, (date, datetime))
        else str(fecha)
    )

    elems.append(
        Paragraph(
            f"<b>Alumno:</b> {alumno} &nbsp;&nbsp; "
            f"<b>Fecha:</b> {f_str} &nbsp;&nbsp; "
            f"<b>Hora:</b> {hora}",
            st_body,
        )
    )
    elems.append(Spacer(1, 6))

    elems.append(
        Paragraph(
            f"<b>Profesor:</b> {profesor}",
            st_body,
        )
    )
    elems.append(Spacer(1, 10))

    desc_html = (descripcion or "").replace("\n", "<br/>")
    elems.append(
        Paragraph(
            f"<b>Descripción:</b><br/>{desc_html}",
            st_body,
        )
    )
    elems.append(Spacer(1, 10))

    elems.append(
        Paragraph(
            f"<b>Gravedad (inicial):</b> {gravedad_inicial}",
            st_body,
        )
    )
    elems.append(Spacer(1, 6))

    if gravedad_final:
        elems.append(
            Paragraph(
                f"<b>Gravedad (final):</b> {gravedad_final}",
                st_body,
            )
        )
        elems.append(Spacer(1, 10))
    else:
        elems.append(Spacer(1, 10))

    elems.append(
        Paragraph(
            f"<i>*** Enviado a Jefatura el "
            f"{enviado_dt.strftime('%d/%m/%Y')} "
            f"a las {enviado_dt.strftime('%H:%M')} "
            f"por {enviado_por} ***</i>",
            st_body,
        )
    )

    doc.build(elems)
    return buf.getvalue()
