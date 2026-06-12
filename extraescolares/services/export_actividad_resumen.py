"""Datos compartidos y exportación Excel del resumen de actividad extraescolar."""

from __future__ import annotations

from extraescolares.calendar_view import format_date_es
from utils.xlsx_export import simple_table_xlsx_bytes


def actividad_resumen_pairs(act: dict) -> list[list[str]]:
    """Filas etiqueta / valor del resumen de la actividad."""
    fecha = format_date_es(act["fecha"]) if act.get("fecha") else "—"
    return [
        ["Actividad", (act.get("actividad") or "").strip()],
        ["Fecha", fecha],
        ["Lugar", (act.get("lugar") or "").strip() or "—"],
        ["Departamento", (act.get("departamento") or "").strip() or "—"],
        ["Horas de ausencia", (act.get("hours_display") or "—")],
        ["Responsable", (act.get("responsable_name") or "").strip() or "—"],
        ["Acompañantes", (act.get("acompanantes_names") or "").strip() or "—"],
        ["Estado", (act.get("status_label") or "—")],
        [
            "Alumnado",
            f"{int(act.get('total_alumnos') or 0)} inscrito(s)"
            f" · {int(act.get('confirmados') or 0)} confirmado(s)",
        ],
    ]


def actividad_resumen_xlsx_bytes(act: dict) -> bytes:
    """XLSX con resumen y listado de alumnado (grupo y nombre)."""
    rows = list(actividad_resumen_pairs(act))
    rows.append(["", ""])
    rows.append(["Grupo", "Alumno/a"])
    students = act.get("students") or []
    if students:
        for s in students:
            rows.append(
                [
                    (s.get("grupo") or "").strip() or "—",
                    (s.get("alumno") or "").strip() or "—",
                ]
            )
    else:
        rows.append(["—", "Sin alumnado inscrito"])

    sheet = ((act.get("actividad") or "Actividad").strip() or "Actividad")[:31]
    return simple_table_xlsx_bytes(
        sheet_name=sheet,
        headers=["Campo", "Valor"],
        rows=rows,
    )
