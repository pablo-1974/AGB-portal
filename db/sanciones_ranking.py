"""Agregación de días de sanción (PAA + expedientes) para rankings."""

from __future__ import annotations

from collections import Counter
from datetime import date

from db.expedientes_disciplinarios import list_expedientes_disciplinarios
from db.paa_procedimientos import list_paa_procedimientos
from reservas.calendar import count_school_days


def _as_date(value) -> date | None:
    if isinstance(value, date):
        return value
    return None


def _add_school_days(counter: Counter, key: str, start: date | None, end: date | None) -> None:
    """Suma días lectivos del rango [start, end] inclusive (ambos extremos cuentan)."""
    if not key or start is None or end is None:
        return
    if start > end:
        return
    # count_school_days ya incluye inicio y fin.
    counter[key] += count_school_days(start, end)


def ranking_dias_sancion(
    *,
    mode: str,
    grupo: str | None = None,
) -> list[dict]:
    """
    Ranking por alumno o por grupo de días de sanción.

    Fuentes:
    - Procedimientos PAA (fecha_inicio .. fecha_final)
    - Expedientes: sanción cautelar y sanción definitiva (si existen)
    """
    mode = (mode or "").strip().lower()
    if mode not in {"alumnos", "grupos"}:
        return []

    grupo_f = (grupo or "").strip() or None
    counter: Counter = Counter()
    alumno_grupo: dict[str, str] = {}

    for row in list_paa_procedimientos():
        alumno = str(row.get("alumno") or "").strip()
        g = str(row.get("grupo") or "").strip()
        if not alumno:
            continue
        if grupo_f and g != grupo_f:
            continue
        if mode == "alumnos":
            key = alumno
            if g:
                alumno_grupo[key] = g
        else:
            key = g
            if not key:
                continue
        _add_school_days(
            counter,
            key,
            _as_date(row.get("fecha_inicio")),
            _as_date(row.get("fecha_final")),
        )

    for row in list_expedientes_disciplinarios():
        alumno = str(row.get("alumno") or "").strip()
        g = str(row.get("grupo") or "").strip()
        if not alumno:
            continue
        if grupo_f and g != grupo_f:
            continue
        if mode == "alumnos":
            key = alumno
            if g:
                alumno_grupo[key] = g
        else:
            key = g
            if not key:
                continue
        _add_school_days(
            counter,
            key,
            _as_date(row.get("cautelar_inicio")),
            _as_date(row.get("cautelar_final")),
        )
        _add_school_days(
            counter,
            key,
            _as_date(row.get("sancion_inicio")),
            _as_date(row.get("sancion_final")),
        )

    if mode == "alumnos":
        return [
            {
                "nombre": alumno,
                "grupo": alumno_grupo.get(alumno),
                "total": total,
            }
            for alumno, total in counter.most_common()
            if total > 0
        ]

    return [
        {"nombre": k, "total": v}
        for k, v in counter.most_common()
        if v > 0
    ]
