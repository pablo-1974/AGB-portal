"""Normas de uso de la app de actividades extraescolares (contenido para plantillas)."""

from __future__ import annotations

# Secciones alineadas con el cuaderno del profesor y la lógica de la app.
NORMAS_EXTRAESCOLARES_SECTIONS: tuple[dict[str, object], ...] = (
    {
        "title": "1. Qué actividades se pueden organizar",
        "points": (
            (
                "Todas las actividades deben estar incluidas en la PGA o ser aprobadas "
                "explícitamente por el Consejo Escolar del Centro."
            ),
            (
                "Su planificación incluye la cumplimentación de la documentación y, tras su "
                "realización, debe adjuntarse una memoria al Departamento de Extraescolares."
            ),
        ),
    },
    {
        "title": "2. Cómo registrar la actividad en la app",
        "points": (
            (
                "El promotor debe consignar la actividad en esta aplicación, incluyendo fecha, "
                "horas de ausencia del centro, profesores acompañantes, alumnado y resto de detalles."
            ),
            (
                "La fecha de la actividad debe ser futura y dentro del curso escolar."
            ),
            (
                "Existe un calendario en la app para consultar todas las actividades programadas "
                "y los alumnos asistentes."
            ),
        ),
    },
    {
        "title": "3. Jefatura, sancionados y listados",
        "points": (
            (
                "Previo a la fecha de realización, el departamento organizador facilitará la lista "
                "de alumnos previstos a Jefatura de Estudios para revisión de incidencias de "
                "comportamiento y de posibles alumnos sancionados."
            ),
            (
                "Antes de la actividad debe entregarse en la administración del centro el listado "
                "de alumnos para que el personal pueda consignarlo en las aplicaciones de la Junta."
            ),
        ),
    },
    {
        "title": "4. Autorizaciones de las familias",
        "points": (
            (
                "Ningún alumno podrá salir del centro sin la autorización firmada por alguno de "
                "sus tutores legales."
            ),
            (
                "Es obligación del profesor organizador facilitar las autorizaciones a los alumnos "
                "y recogerlas antes de la realización de la actividad."
            ),
            (
                "El plazo para que el alumno entregue la autorización firmada expira el día lectivo "
                "anterior al de la actividad."
            ),
            (
                "En la app hay un modelo tipo de autorización en PDF que se puede generar de forma "
                "sencilla (recomendable)."
            ),
        ),
    },
    {
        "title": "5. Confirmación y anulación en la app",
        "points": (
            (
                "Antes de la realización, la actividad debe ser confirmada por el promotor en "
                "«Mis actividades» para que conste como definitiva."
            ),
            (
                "La confirmación puede hacerse hasta el día anterior a la fecha de la actividad "
                "(no el mismo día)."
            ),
            (
                "Si hay actividades próximas sin confirmar, la app puede avisar en el portal "
                "(con unos 15 días de antelación)."
            ),
            (
                "Mientras no esté confirmada ni anulada, el organizador puede editarla si la fecha "
                "aún no ha pasado. Tras confirmarla, solo Jefatura/Administración puede modificarla "
                "según permisos."
            ),
            (
                "El organizador puede anular una actividad futura desde «Mis actividades» si aún "
                "no se ha celebrado."
            ),
        ),
    },
)
