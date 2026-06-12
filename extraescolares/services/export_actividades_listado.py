"""Exportación del listado completo de actividades extraescolares del curso."""

from __future__ import annotations

from consultas.listados.pdf_list import (
    generate_multi_simple_table_pdf_bytes,
    generate_simple_table_pdf_bytes,
)
from context import institution_display_name
from config import settings
from utils.docx_export import simple_table_docx_bytes
from utils.xlsx_export import simple_table_xlsx_bytes

LIST_HEADERS = [
    "Sección",
    "Fecha",
    "Actividad",
    "Responsable",
    "Departamento",
    "Lugar",
    "Horas",
    "Alumnado",
    "Estado",
    "Grupos",
]


def _estado_actividad(act: dict) -> str:
    return act.get("status_label") or "—"


def _actividad_list_row(act: dict, section: str) -> list[str]:
    return [
        section,
        act.get("fecha_display") or "",
        (act.get("actividad") or "").strip(),
        (act.get("responsable_name") or "").strip(),
        (act.get("departamento") or "").strip() or "—",
        (act.get("lugar") or "").strip() or "—",
        act.get("hours_display") or "—",
        f"{int(act.get('confirmados') or 0)} / {int(act.get('total_alumnos') or 0)}",
        _estado_actividad(act),
        (act.get("grupos_label") or "").strip() or "—",
    ]


def actividades_listado_rows(
    programadas: list[dict],
    realizadas: list[dict],
) -> list[list[str]]:
    rows: list[list[str]] = []
    for act in programadas:
        rows.append(_actividad_list_row(act, "Programada"))
    for act in realizadas:
        rows.append(_actividad_list_row(act, "Realizada"))
    return rows


def actividades_listado_title(year_label: str) -> str:
    centro = institution_display_name(settings.INSTITUTION_NAME)
    curso = (year_label or "").strip()
    if curso:
        return f"Actividades extraescolares · {centro} · {curso}"
    return f"Actividades extraescolares · {centro}"


def actividades_listado_pdf_bytes(
    *,
    year_label: str,
    programadas: list[dict],
    realizadas: list[dict],
) -> bytes:
    center = institution_display_name(settings.INSTITUTION_NAME)
    title = actividades_listado_title(year_label)
    prog_rows = [_actividad_list_row(a, "Programada") for a in programadas]
    real_rows = [_actividad_list_row(a, "Realizada") for a in realizadas]

    if prog_rows and real_rows:
        return generate_multi_simple_table_pdf_bytes(
            center_name=center,
            sections=[
                ("Actividades programadas", LIST_HEADERS, prog_rows),
                ("Actividades realizadas", LIST_HEADERS, real_rows),
            ],
        )
    all_rows = prog_rows + real_rows
    if not all_rows:
        all_rows = [["—"] * len(LIST_HEADERS)]
    return generate_simple_table_pdf_bytes(
        center_name=center,
        headline=title,
        headers=LIST_HEADERS,
        rows=all_rows,
    )


def actividades_listado_xlsx_bytes(
    *,
    year_label: str,
    programadas: list[dict],
    realizadas: list[dict],
) -> bytes:
    rows = actividades_listado_rows(programadas, realizadas)
    if not rows:
        rows = [["—"] * len(LIST_HEADERS)]
    sheet = (year_label or "Actividades")[:31]
    return simple_table_xlsx_bytes(
        sheet_name=sheet,
        headers=LIST_HEADERS,
        rows=rows,
    )


def actividades_listado_docx_bytes(
    *,
    year_label: str,
    programadas: list[dict],
    realizadas: list[dict],
) -> bytes:
    rows = actividades_listado_rows(programadas, realizadas)
    if not rows:
        rows = [["—"] * len(LIST_HEADERS)]
    return simple_table_docx_bytes(
        title=actividades_listado_title(year_label),
        headers=LIST_HEADERS,
        rows=rows,
    )
