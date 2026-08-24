"""Normas de uso de la app de incidencias (contenido para plantillas)."""

from __future__ import annotations

# Secciones alineadas con el cuaderno del profesor y la lógica de la app.
NORMAS_INCIDENCIAS_SECTIONS: tuple[dict[str, object], ...] = (
    {
        "title": "1. Qué es un parte de incidencias",
        "points": (
            (
                "Los partes de incidencias se clasifican en leves, graves y muy graves, "
                "siguiendo el Reglamento de Régimen Interior (RRI) del centro."
            ),
            (
                "Se comunican a Jefatura de Estudios a través de esta aplicación de gestión."
            ),
            (
                "El hecho de poner un parte no supone que el alumno sea expulsado del aula; "
                "la expulsión es una medida excepcional."
            ),
        ),
    },
    {
        "title": "2. Cómo registrar un parte en la app",
        "points": (
            (
                "Indique alumno (o varios del mismo grupo), fecha, franja horaria, gravedad "
                "inicial y descripción de los hechos."
            ),
            (
                "La fecha debe ser de hoy o anterior, y corresponder a un día lectivo "
                "(no festivos ni no lectivos del calendario escolar)."
            ),
            (
                "Tras enviarlo a Jefatura, el parte queda abierto. El cierre y la gravedad "
                "final los determina Jefatura."
            ),
        ),
    },
    {
        "title": "3. Expulsión del aula (medida excepcional)",
        "points": (
            (
                "Si un alumno es expulsado del aula, debe ser enviado a la Sala de Visitas "
                "para que lo atienda un profesor de guardia."
            ),
            (
                "La expulsión se considera falta grave y así debe constar en el parte."
            ),
            (
                "El alumno expulsado debe llevar a la Sala de Visitas un documento de "
                "comunicación para el profesor de guardia con el motivo de la expulsión, "
                "para que este comunique telefónicamente la expulsión a la familia."
            ),
            (
                "El alumno expulsado debe llevar trabajo para realizar en el aula de expulsados."
            ),
            (
                "Si el profesor que pone el parte quiere comunicarlo además a la familia, "
                "puede hacerlo por la aplicación de Comunicaciones de Stilus o por teléfono."
            ),
        ),
    },
    {
        "title": "4. Seguimiento y tutoría",
        "points": (
            (
                "Los profesores pueden consultar sus partes en «Mis incidencias». "
                "Los tutores disponen además de «Mi tutoría», donde consultar el historial "
                "de incidencias de sus alumnos tutelados."
            ),
            (
                "El tutor debe comunicar a la familia el número de partes que tienen los "
                "alumnos a partir de cinco."
            ),
        ),
    },
)
