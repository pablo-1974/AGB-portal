"""Documentación de variables de cálculo (Evaluación de competencias).

Añadir aquí cada variable nueva para que aparezca en /competencias/calculos/variables.

Los valores se guardan en tablas (``competencias_materia_variables``,
``competencias_materia_pd_porcentajes``, catálogo ``phoras``) y **no se
recalculan al arrancar ni al abrir pantallas**. Solo se regeneran en cadena
cuando cambia un dato de origen: porcentajes de la PD, horas/phoras del
catálogo o descriptores de una competencia clave.
"""

from __future__ import annotations

from typing import TypedDict


class VariableDoc(TypedDict):
    nombre: str
    ambito: str
    formula: str
    descripcion: str
    ejemplo: str


# Ámbitos: materia | descriptor | descriptor_criterio | alumno_materia
VARIABLES_CALCULO: tuple[VariableDoc, ...] = (
    {
        "nombre": "phoras",
        "ambito": "materia",
        "formula": "horas semanales ÷ 30",
        "descripcion": (
            "Peso horario de la materia respecto a una jornada de 30 horas semanales. "
            "Se guarda en el catálogo (phoras) y en competencias_materia_variables. "
            "Solo se recalcula si cambian las horas de la materia."
        ),
        "ejemplo": "Historia de España (4 h/semana): 4/30 = 0,13.",
    },
    {
        "nombre": "sumcoef1",
        "ambito": "materia",
        "formula": "Σ coef1 de todos los pares descriptor × criterio",
        "descripcion": (
            "Suma de todos los coef1 de la materia. Se repite el mismo valor "
            "en todas las filas de esa materia."
        ),
        "ejemplo": (
            "Suma de todos los coef1; en Historia de España ≈ 16,13."
        ),
    },
    {
        "nombre": "cruce",
        "ambito": "descriptor_criterio",
        "formula": "1 si hay cruce; 0 si no",
        "descripcion": (
            "Indica si un descriptor operativo está vinculado a un criterio de "
            "evaluación concreto de la materia (según el currículo)."
        ),
        "ejemplo": "Si CCL 1 aparece en el criterio 1.1 → cruce = 1; si no → 0.",
    },
    {
        "nombre": "ppd",
        "ambito": "descriptor_criterio",
        "formula": "% del criterio en la programación didáctica",
        "descripcion": (
            "Porcentaje que la materia otorga a ese criterio en la PD. "
            "Es el valor que se edita en la ficha de la materia "
            "(Materias → detalle). Se repite en todas las filas del mismo criterio. "
            "Si la asignatura se evalúa como pendiente y los pesos pendientes "
            "son distintos, se usan esos porcentajes."
        ),
        "ejemplo": "Si el criterio 1.1 pesa un 5 % en la PD → ppd = 5.",
    },
    {
        "nombre": "dototal",
        "ambito": "descriptor",
        "formula": "Σ (cruce × ppd) sobre todos los criterios",
        "descripcion": (
            "Suma, para un descriptor operativo, de los productos cruce×ppd "
            "de cada criterio de la materia. Mide cuánto peso de la PD "
            "«toca» ese descriptor."
        ),
        "ejemplo": "En Historia de España, para CCL 1 → dototal = 42.",
    },
    {
        "nombre": "donumcru",
        "ambito": "descriptor",
        "formula": "nº de criterios con cruce = 1",
        "descripcion": (
            "Número de criterios de evaluación de la materia con los que "
            "cruza el descriptor operativo."
        ),
        "ejemplo": "En Historia de España, para CCL 1 → donumcru = 6.",
    },
    {
        "nombre": "coef0",
        "ambito": "descriptor_criterio",
        "formula": "cruce × ppd × donumcru ÷ dototal",
        "descripcion": (
            "Coeficiente del par descriptor–criterio que reparte el peso "
            "del descriptor según el % del criterio y el número de cruces."
        ),
        "ejemplo": "En Historia, CCL 2 y criterio 1.1 → coef0 ≈ 0,34.",
    },
    {
        "nombre": "coef1",
        "ambito": "descriptor_criterio",
        "formula": "coef0 × phoras",
        "descripcion": (
            "Mismo coeficiente ponderado por el peso horario de la materia."
        ),
        "ejemplo": "Con coef0 ≈ 0,34 y phoras = 0,13 → coef1 ≈ 0,05.",
    },
    {
        "nombre": "coef2",
        "ambito": "descriptor_criterio",
        "formula": "coef1 ÷ sumcoef1",
        "descripcion": (
            "Proporción que representa ese coef1 respecto a la suma de todos "
            "los coef1 de la materia."
        ),
        "ejemplo": (
            "En Historia, sumcoef1 ≈ 16,13; para CCL 2 y criterio 1.1 "
            "(coef1 ≈ 0,05) → coef2 = 0,05/16,13."
        ),
    },
    {
        "nombre": "nota_comp",
        "ambito": "alumno_materia",
        "formula": "Σ (calificación × ppd) ÷ 100",
        "descripcion": (
            "Nota de competencias del alumno en la materia. Se calcula al vuelo "
            "en Calificar a partir de las calificaciones por criterio y del "
            "porcentaje de cada criterio en la PD. Se muestra con un decimal."
        ),
        "ejemplo": (
            "Si el criterio 1.1 (ppd = 40) tiene un 8 y el 1.2 (ppd = 60) un 5 → "
            "nota_comp = (8×40 + 5×60) / 100 = 6,2."
        ),
    },
    {
        "nombre": "suma_nota_0",
        "ambito": "alumno_descriptor",
        "formula": "Σ (calificación × coef0) en todas las asignaturas del alumno",
        "descripcion": (
            "Suma, para un descriptor operativo, de los productos calificación×coef0 "
            "en cada criterio de cada asignatura que cursa el alumno. "
            "Se guarda en competencias_alumno_descriptor_notas y se recalcula al "
            "guardar notas, cambiar coeficientes de materia, descriptores o matrículas."
        ),
        "ejemplo": "Suma ponderada de las calificaciones por criterio con coef0.",
    },
    {
        "nombre": "suma_coef_0",
        "ambito": "alumno_descriptor",
        "formula": "Σ (cruce × coef0) en todas las asignaturas del alumno",
        "descripcion": (
            "Suma de los productos cruce×coef0 (cruce 0 o 1) en cada criterio "
            "de cada asignatura del alumno, para el mismo descriptor operativo."
        ),
        "ejemplo": "Denominador de nota_do_0.",
    },
    {
        "nombre": "nota_do_0",
        "ambito": "alumno_descriptor",
        "formula": "suma_nota_0 ÷ suma_coef_0",
        "descripcion": (
            "Nota del alumno en el descriptor operativo según coef0. "
            "Vacía si suma_coef_0 es 0."
        ),
        "ejemplo": "Media ponderada con coef0 y calificaciones por criterio.",
    },
    {
        "nombre": "nota_do_1",
        "ambito": "alumno_descriptor",
        "formula": "suma_nota_1 ÷ suma_coef_1",
        "descripcion": (
            "Igual que nota_do_0 usando coef1 (suma_nota_1 y suma_coef_1)."
        ),
        "ejemplo": "Media ponderada con coef1.",
    },
    {
        "nombre": "nota_do_2",
        "ambito": "alumno_descriptor",
        "formula": "suma_nota_2 ÷ suma_coef_2",
        "descripcion": (
            "Igual que nota_do_0 usando coef2 (suma_nota_2 y suma_coef_2)."
        ),
        "ejemplo": "Media ponderada con coef2.",
    },
    {
        "nombre": "nota_cc_0",
        "ambito": "alumno_competencia",
        "formula": "Σ suma_nota_0 de los descriptores de la competencia ÷ Σ suma_coef_0",
        "descripcion": (
            "Nota de una competencia clave (p. ej. CCL) cuando no se usa el promedio "
            "de descriptores. Agrupa los descriptores de esa competencia "
            "(CCL 1 a CCL 5) y divide la suma de suma_nota_0 entre la suma de "
            "suma_coef_0. Se guarda en competencias_alumno_competencia_notas. "
            "Se muestra si Configuración → Cálculo usa coef0 "
            "(cruces y % departamento) y promedio = No."
        ),
        "ejemplo": "CCL: (suma_nota_0 de CCL1…CCL5) / (suma_coef_0 de CCL1…CCL5).",
    },
    {
        "nombre": "nota_cc_1",
        "ambito": "alumno_competencia",
        "formula": "Σ suma_nota_1 ÷ Σ suma_coef_1 de los descriptores de la competencia",
        "descripcion": (
            "Igual que nota_cc_0 con coef1 (cruces, % departamento y horas)."
        ),
        "ejemplo": "Misma agregación que nota_cc_0 usando las columnas _1.",
    },
    {
        "nombre": "nota_cc_2",
        "ambito": "alumno_competencia",
        "formula": "Σ suma_nota_2 ÷ Σ suma_coef_2 de los descriptores de la competencia",
        "descripcion": (
            "Igual que nota_cc_0 con coef2 (% departamento y horas, sin cantidad de cruces)."
        ),
        "ejemplo": "Misma agregación que nota_cc_0 usando las columnas _2.",
    },
    {
        "nombre": "nota_cc_prom_0",
        "ambito": "alumno_competencia",
        "formula": "media aritmética de nota_do_0 de los descriptores de la competencia",
        "descripcion": (
            "Nota de una competencia clave cuando Configuración evalúa cada "
            "competencia como promedio de sus descriptores operativos. "
            "Solo entra en el promedio los descriptores con nota_do_0. "
            "Se muestra con coef0 si además se elige la opción de cruces y %."
        ),
        "ejemplo": "CCL: promedio de nota_do_0 de CCL 1, CCL 2, CCL 3, CCL 4 y CCL 5.",
    },
    {
        "nombre": "nota_cc_prom_1",
        "ambito": "alumno_competencia",
        "formula": "media aritmética de nota_do_1 de los descriptores de la competencia",
        "descripcion": "Igual que nota_cc_prom_0 usando nota_do_1 (coef1).",
        "ejemplo": "Promedio de los nota_do_1 de los descriptores de esa competencia.",
    },
    {
        "nombre": "nota_cc_prom_2",
        "ambito": "alumno_competencia",
        "formula": "media aritmética de nota_do_2 de los descriptores de la competencia",
        "descripcion": "Igual que nota_cc_prom_0 usando nota_do_2 (coef2).",
        "ejemplo": "Promedio de los nota_do_2 de los descriptores de esa competencia.",
    },
    {
        "nombre": "nota_acta",
        "ambito": "alumno_materia",
        "formula": "calificación final introducida a mano",
        "descripcion": (
            "Nota oficial del alumno en la materia para Stilus y el acta de papel. "
            "En ESO es cualitativa (IN, SU, BI, NT, SB). En Bachillerato es un entero "
            "de 0 a 10, sin decimales. No se calcula a partir de los criterios: se "
            "rellena a mano en Calificar (cuadrado «acta»)."
        ),
        "ejemplo": "En ESO, si el acta debe figurar Notable, se elige NT. En Bachillerato, un 7 se escribe 7.",
    },
)

AMBITO_LABELS: dict[str, str] = {
    "materia": "Por materia",
    "descriptor": "Por descriptor operativo (dentro de la materia)",
    "descriptor_criterio": "Por descriptor operativo × criterio de evaluación",
    "alumno_materia": "Por alumno × materia",
    "alumno_descriptor": "Por alumno × descriptor operativo",
    "alumno_competencia": "Por alumno × competencia clave",
}

AMBITO_ORDER: tuple[str, ...] = (
    "materia",
    "descriptor",
    "descriptor_criterio",
    "alumno_materia",
    "alumno_descriptor",
    "alumno_competencia",
)


def variables_por_ambito() -> list[dict]:
    """Grupos listos para la plantilla."""
    by: dict[str, list[VariableDoc]] = {k: [] for k in AMBITO_ORDER}
    for v in VARIABLES_CALCULO:
        by.setdefault(v["ambito"], []).append(v)
    out: list[dict] = []
    for key in AMBITO_ORDER:
        items = by.get(key) or []
        if not items:
            continue
        out.append(
            {
                "ambito": key,
                "titulo": AMBITO_LABELS.get(key, key),
                "variables": items,
            }
        )
    return out
