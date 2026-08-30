"""Alumnado seleccionado para asignación de puestos."""

from __future__ import annotations

from db.students import get_student_by_id
from utils.text import normalize_for_sort


def parse_student_ids(raw_values: list[str] | tuple[str, ...]) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for raw in raw_values:
        try:
            sid = int(raw)
        except (TypeError, ValueError):
            continue
        if sid in seen:
            continue
        if get_student_by_id(sid):
            seen.add(sid)
            ids.append(sid)
    return ids


def list_alumnos_para_puestos(student_ids: list[int]) -> list[dict[str, object]]:
    """Opciones de desplegable: nombre del alumno y grupo, orden alfabético."""
    rows: list[dict[str, object]] = []
    for sid in student_ids:
        student = get_student_by_id(sid)
        if not student:
            continue
        alumno = str(student.get("alumno") or "").strip()
        grupo = str(student.get("grupo") or "").strip()
        if not alumno:
            continue
        label = f"{alumno} ({grupo})" if grupo else alumno
        rows.append(
            {
                "id": int(student["id"]),
                "label": label,
                "alumno": alumno,
                "grupo": grupo,
            }
        )
    rows.sort(key=lambda r: normalize_for_sort(str(r["alumno"])))
    return rows
