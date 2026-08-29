"""Normas de uso de la app Aula de Informática (contenido para plantillas)."""

from __future__ import annotations

NORMAS_AULA_INFORMATICA_SECTIONS: tuple[dict[str, object], ...] = (
    {
        "title": "1. Obligatorio",
        "points": (
            "Si acude con alumnos a un aula de informática (A, B, C o Multimedia), debe completar el informe en esta aplicación.",
            "Aquí se registra el puesto de cada alumno y el estado del equipo; no sustituye a la reserva del aula ni a otras normas del centro.",
        ),
    },
    {
        "title": "2. Cómo registrar (En el aula)",
        "points": (
            "Pulse En el aula en el menú, elija el aula, la fecha y la hora de la sesión.",
            "Seleccione los grupos y los alumnos presentes.",
            "Asigne un puesto a cada alumno e indique si el equipo está en buen estado o con incidencias (describa la incidencia si procede).",
            "Revise el resumen, complete Otras incidencias si hace falta, y envíe el informe.",
        ),
    },
    {
        "title": "3. Cambios durante la clase (Mis registros)",
        "points": (
            "Si durante la misma hora un alumno cambia de puesto o aparecen nuevas incidencias, edite el registro en Mis registros (icono del lápiz).",
            "Puede asignar el mismo alumno en varios puestos si ha cambiado de sitio, para dejar constancia de todos los equipos que ha usado.",
            "Puede modificar el alumno de un puesto, el estado, las incidencias por puesto y el campo Otras incidencias; guarde los cambios al terminar.",
        ),
    },
)
