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


def _add_days(counter: Counter, key: str, dias: int) -> None:
    if key and dias > 0:
        counter[key] += dias


def _paa_dias_lectivos(row: dict) -> int:
    """Días ya calculados al registrar el PAA; fallback por fechas si hace falta."""
    stored = row.get("dias_lectivos")
    if stored is not None:
        d = int(stored)
        if d > 0:
            return d
    fi = _as_date(row.get("fecha_inicio"))
    ff = _as_date(row.get("fecha_final"))
    if fi and ff and fi <= ff:
        return count_school_days(fi, ff)
    return 0


def _expediente_dias_lectivos(row: dict) -> int:
    """Total cautelar + definitiva guardado en el expediente; fallback por fechas."""
    d = int(row.get("dias_lectivos") or 0)
    if d > 0:
        return d
    total = 0
    ci = _as_date(row.get("cautelar_inicio"))
    cf = _as_date(row.get("cautelar_final"))
    si = _as_date(row.get("sancion_inicio"))
    sf = _as_date(row.get("sancion_final"))
    if ci and cf and ci <= cf:
        total += count_school_days(ci, cf)
    if si and sf and si <= sf:
        total += count_school_days(si, sf)
    return total


def ranking_dias_sancion(
    *,
    mode: str,
    grupo: str | None = None,
) -> list[dict]:
    """
    Ranking por alumno o por grupo de días de sanción.

    Fuentes:
    - Procedimientos PAA (dias_lectivos)
    - Expedientes disciplinarios (dias_lectivos = cautelar + definitiva)
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
        _add_days(counter, key, _paa_dias_lectivos(row))

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
        _add_days(counter, key, _expediente_dias_lectivos(row))

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
