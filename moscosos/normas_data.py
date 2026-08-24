"""Normas de uso y reserva de moscosos (contenido para plantillas)."""

from __future__ import annotations

# Secciones alineadas con la lógica de la app y el cuaderno del profesor (Anexo I).
NORMAS_RESERVA_SECTIONS: tuple[dict[str, object], ...] = (
    {
        "title": "1. Qué es esta aplicación",
        "points": (
            (
                "Sirve para reservar el día de asuntos de interés particular (moscoso) "
                "y para tramitar la solicitud del permiso (Anexo I)."
            ),
            (
                "No se puede solicitar un moscoso si no se dispone de la reserva del mismo "
                "en el calendario de esta aplicación."
            ),
        ),
    },
    {
        "title": "2. Cuántos moscosos y plazas por día",
        "points": (
            (
                "Cada persona puede tener como máximo dos reservas en el curso escolar, "
                "y deben ser en trimestres distintos (no dos reservas en el mismo trimestre)."
            ),
            (
                "En cada día lectivo reservable solo hay dos plazas. Si ya hay dos reservas "
                "de compañeros ese día, no se puede reservar esa fecha: habrá que elegir otro día "
                "disponible en verde."
            ),
            (
                "La concesión está sujeta a la organización del centro. No se conceden moscosos "
                "en los días señalados en la Orden, en los coincidentes con las pruebas de EBAU "
                "ni si hubiera una actividad extraescolar esos días (aparecen no disponibles "
                "o excluidos en el calendario)."
            ),
        ),
    },
    {
        "title": "3. Antelación para reservar",
        "points": (
            (
                "Solo se puede reservar en los días que aparecen en verde en el calendario."
            ),
            (
                "Hay que reservar con al menos diez días de antelación: hoy y los nueve días "
                "siguientes no están disponibles para nueva reserva."
            ),
            (
                "La reserva puede hacerse con un máximo de tres meses de antelación, "
                "y en todo caso hasta el último día de clases del curso."
            ),
        ),
    },
    {
        "title": "4. Documentación (Anexo I): cuándo y cómo enviarla",
        "points": (
            (
                "La solicitud del permiso (Anexo I) debe enviarse entre quince y siete días "
                "antes de la fecha reservada. Si no se envía en plazo, no podrá tramitarse "
                "y no se podrá disfrutar del moscoso."
            ),
            (
                "El envío se hace desde esta aplicación (enlace «Reservar», icono del sobre ✉️), "
                "adjuntando el Anexo I en PDF."
            ),
            (
                "Rellene el Anexo I marcando la casilla «Otros» y, en Observaciones, "
                "«Asunto de interés particular»."
            ),
            (
                "Fírmelo digitalmente con el certificado electrónico y deje el documento abierto "
                "para que pueda firmarlo después el Director Provincial. "
                "IMPORTANTE: no cierre el PDF después de firmarlo digitalmente."
            ),
            (
                "Nombre el archivo con: APELLIDOS, NOMBRE – CENTRO – FECHA. "
                "Ejemplo: FAJARDO LÓPEZ, ANTONIO – IES ANTONIO GARCÍA BELLIDO – 09-09-2026."
            ),
            (
                "Una vez enviada la documentación, la reserva queda bloqueada y ya no se puede anular."
            ),
        ),
    },
    {
        "title": "5. Si finalmente no va a solicitar el permiso",
        "points": (
            (
                "Libere la reserva desde «Reservar» mientras aún no haya enviado la documentación, "
                "para que otro compañero pueda usar esa plaza."
            ),
        ),
    },
)

# Lista plana (compatibilidad / vistas simples).
NORMAS_RESERVA_MOSCOSOS: tuple[str, ...] = tuple(
    point
    for section in NORMAS_RESERVA_SECTIONS
    for point in section["points"]  # type: ignore[union-attr]
)
