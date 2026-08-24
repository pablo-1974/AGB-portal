"""Normas de uso de la app de Evaluación de competencias."""

from __future__ import annotations

NORMAS_COMPETENCIAS_SECTIONS: tuple[dict[str, object], ...] = (
    {
        "title": "1. Para qué sirve esta aplicación",
        "points": (
            (
                "Esta app registra las calificaciones por criterios de evaluación y calcula "
                "las competencias clave LOMLOE del alumnado de ESO y Bachillerato."
            ),
            (
                "No sustituye a Stilus ni a otras aplicaciones oficiales de la Junta: las "
                "notas que introduzcas aquí alimentan el cálculo de competencias del centro."
            ),
            (
                "El acceso es personal e intransferible. No uses la cuenta de otra persona "
                "ni dejes la sesión abierta en un equipo compartido."
            ),
        ),
    },
    {
        "title": "2. Pesos de los criterios de evaluación",
        "points": (
            (
                "Los jefes de departamento deben introducir los pesos de los criterios de "
                "evaluación de sus materias tal y como aparecen en las programaciones didácticas."
            ),
        ),
    },
    {
        "title": "3. Calificar",
        "points": (
            (
                "Cada profesor debe calificar los criterios de evaluación de cada uno de "
                "sus alumnos. Esas notas son la base del cálculo de descriptores y competencias."
            ),
            (
                "Cada profesor debe introducir la nota final en la materia, la misma que "
                "grabe en Stilus."
            ),
            (
                "El plazo para introducir o modificar calificaciones termina el día anterior "
                "a la sesión de evaluación, a las 23:55 (hora de Madrid). Después la app no "
                "permite guardar cambios."
            ),
            (
                "Califica solo al alumnado de tus grupos y materias. Si una materia no te "
                "aparece, revisa el horario o consulta con Jefatura."
            ),
            (
                "En Bachillerato hay sesión ordinaria y extraordinaria. Las notas de la "
                "ordinaria quedan congeladas al pasar a extraordinaria para no perderse."
            ),
            (
                "Puedes usar la plantilla Excel de la materia para cargar notas. Debes "
                "descargar el excel en blanco, rellenarlo en tu ordenador e importarlo a la "
                "aplicación, y esperar mientras esta importa las calificaciones; tarda unos "
                "segundos y, cuando finaliza, da un mensaje."
            ),
        ),
    },
    {
        "title": "4. Evaluaciones",
        "points": (
            (
                "En Evaluaciones se consultan, por grupo, las notas de materia y de "
                "competencias de cada alumno de los grupos a los que des clase."
            ),
        ),
    },
    {
        "title": "5. Datos y uso responsable",
        "points": (
            (
                "Las calificaciones son datos académicos personales. No las exportes ni "
                "las reenvíes fuera del centro salvo el procedimiento oficial."
            ),
            (
                "Si detectas un error de matrícula, grupo o materia, avisa a Jefatura o "
                "Secretaría: no inventes calificaciones para tapar un descuadre."
            ),
        ),
    },
)
