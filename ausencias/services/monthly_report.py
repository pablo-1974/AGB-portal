"""
Parte mensual: misma lógica que consultas `services/pdf_monthly.py`.

Solo días lectivos; filas catalogadas (categoría ≠ Z). Excluye sustituciones.

Las **excedencias** no generan filas por ``leaves`` (campo ``leave_kind``) ni
por ausencias puntuales si ``users.status`` es excedencia. Las **bajas** sí
figuran si están catalogadas.
"""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from ausencias.absence_categories import (
    category_excluded_from_monthly_report,
    needs_administrative_cataloging,
)
from ausencias.db import list_absences_range, list_leaves
from db.connection import get_db
from reservas.calendar import is_school_day
from utils.text import normalize_for_sort

_HOUR_LABELS = ("1ª", "2ª", "3ª", "Recreo", "4ª", "5ª", "6ª")


def _as_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    s = str(val)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _mask_to_human(mask: int) -> str:
    if mask <= 0:
        return "-"
    on = [i for i in range(7) if (mask >> i) & 1]
    if not on:
        return "-"
    parts: list[str] = []
    start = on[0]
    prev = on[0]
    for idx in on[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        parts.append(_HOUR_LABELS[start] if start == prev else f"{_HOUR_LABELS[start]}-{_HOUR_LABELS[prev]}")
        start = prev = idx
    parts.append(_HOUR_LABELS[start] if start == prev else f"{_HOUR_LABELS[start]}-{_HOUR_LABELS[prev]}")
    return ", ".join(parts)


def _format_date_span(days: list[date]) -> tuple[str, int]:
    if not days:
        return "", 0
    days = sorted(days)
    d0, d1 = days[0], days[-1]
    if d0 == d1:
        return d0.strftime("%d/%m/%Y"), 1
    return (
        f"del {d0.strftime('%d/%m/%Y')} al {d1.strftime('%d/%m/%Y')}",
        (d1 - d0).days + 1,
    )


def _segments(days_sorted_unique: list[date]) -> list[list[date]]:
    """Tramos consecutivos según días lectivos (salta fines de semana y festivos)."""
    if not days_sorted_unique:
        return []
    segment = [days_sorted_unique[0]]
    segments: list[list[date]] = []
    for d in days_sorted_unique[1:]:
        next_day = segment[-1] + timedelta(days=1)
        while not is_school_day(next_day):
            next_day += timedelta(days=1)
        if d == next_day:
            segment.append(d)
        else:
            segments.append(segment)
            segment = [d]
    segments.append(segment)
    return segments


def _fetch_teacher_names(ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    id_list = list(ids)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name
                FROM users
                WHERE id = ANY(%s)
                """,
                (id_list,),
            )
            return {int(r["id"]): str(r["name"] or "").strip() for r in cur.fetchall()}


def _fetch_teacher_status(ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    id_list = list(ids)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, COALESCE(status, 'activo') AS status
                FROM users
                WHERE id = ANY(%s)
                """,
                (id_list,),
            )
            return {int(r["id"]): str(r["status"] or "").strip().lower() for r in cur.fetchall()}


def build_monthly_report(*, date_from: date, date_to: date) -> dict[str, Any]:
    """Filas para vista HTML y PDF; omite por completo a quienes están en excedencia."""
    abs_rows = list_absences_range(from_date=date_from, to_date=date_to)
    by_date: dict[date, list[dict]] = defaultdict(list)
    tid_abs: set[int] = set()
    for a in abs_rows:
        d = _as_date(a.get("date"))
        if d is None:
            continue
        by_date[d].append(a)
        tid_abs.add(int(a["teacher_id"]))

    leaves_all = list_leaves(include_closed=True)
    tid_leave = {int(lv["teacher_id"]) for lv in leaves_all if not lv.get("is_substitution")}
    tid_all_status = tid_abs | tid_leave
    names_by_id = _fetch_teacher_names(tid_all_status)
    status_by_id = _fetch_teacher_status(tid_all_status)

    acc: dict[tuple[str, int, str], list[date]] = defaultdict(list)
    rows_sin_catalogar: list[dict[str, Any]] = []

    cur = date_from
    while cur <= date_to:
        if not is_school_day(cur):
            cur += timedelta(days=1)
            continue

        for a in by_date.get(cur, []):
            tid = int(a["teacher_id"])
            if status_by_id.get(tid) == "excedencia":
                continue
            cat = str(a.get("category") or "").strip()
            nm = str(a.get("teacher_name") or "").strip() or names_by_id.get(tid, f"ID {tid}")
            if needs_administrative_cataloging(cat):
                rows_sin_catalogar.append(
                    {
                        "teacher_name": nm,
                        "fecha_display": cur.strftime("%d/%m/%Y"),
                        "horas": _mask_to_human(int(a.get("hours_mask") or 0)),
                        "causa": "",
                        "catalog_href": f"/ausencias/absences/categorize?from={cur.isoformat()}&to={cur.isoformat()}",
                    }
                )
                continue
            if category_excluded_from_monthly_report(cat):
                continue
            acc[("absence", tid, cat)].append(cur)

        for lv in leaves_all:
            if lv.get("is_substitution"):
                continue
            sd = _as_date(lv.get("start_date"))
            if sd is None or sd > cur:
                continue
            ed = _as_date(lv.get("end_date"))
            if ed is not None and ed < cur:
                continue
            tid = int(lv["teacher_id"])
            if str(lv.get("leave_kind") or "baja").strip().lower() == "excedencia":
                continue
            cat = str(lv.get("category") or "").strip()
            nm = str(lv.get("teacher_name") or "").strip() or names_by_id.get(tid, f"ID {tid}")
            if needs_administrative_cataloging(cat):
                rows_sin_catalogar.append(
                    {
                        "teacher_name": nm,
                        "fecha_display": cur.strftime("%d/%m/%Y"),
                        "horas": "Todas",
                        "causa": str(lv.get("cause") or "").strip(),
                        "catalog_href": "/ausencias/leaves/categorize",
                    }
                )
                continue
            if category_excluded_from_monthly_report(cat):
                continue
            acc[("leave", tid, cat)].append(cur)

        cur += timedelta(days=1)

    rows_catalogadas: list[dict[str, Any]] = []
    pdf_body: list[list[str]] = []

    for (_kind, tid, cat), days in acc.items():
        days_u = sorted(set(days))
        if not days_u:
            continue
        nombre = names_by_id.get(tid, f"ID {tid}")
        for seg in _segments(days_u):
            fecha_text, _ = _format_date_span(seg)
            n_days = len(seg)
            row = {
                "nombre": nombre,
                "fecha": fecha_text,
                "horas": "Todas",
                "causa": cat,
                "dias": str(n_days),
            }
            rows_catalogadas.append(row)
            pdf_body.append([nombre, fecha_text, "Todas", cat, str(n_days)])

    rows_catalogadas.sort(
        key=lambda r: (
            str(r.get("nombre") or ""),
            normalize_for_sort(str(r.get("causa") or "")),
        )
    )
    pdf_body.sort(key=lambda row: (row[0], normalize_for_sort(row[3] or "")))

    has_uncategorized = len(rows_sin_catalogar) > 0

    return {
        "rows_catalogadas": rows_catalogadas,
        "rows_sin_catalogar": rows_sin_catalogar,
        "has_uncategorized": has_uncategorized,
        "pdf_body_rows": pdf_body,
    }


def monthly_pdf_title(date_from: date, date_to: date) -> str:
    ultimo = monthrange(date_from.year, date_from.month)[1]
    mes_completo = (
        date_from.day == 1
        and date_to.day == ultimo
        and date_from.month == date_to.month
        and date_from.year == date_to.year
    )
    meses = {
        1: "ENERO",
        2: "FEBRERO",
        3: "MARZO",
        4: "ABRIL",
        5: "MAYO",
        6: "JUNIO",
        7: "JULIO",
        8: "AGOSTO",
        9: "SEPTIEMBRE",
        10: "OCTUBRE",
        11: "NOVIEMBRE",
        12: "DICIEMBRE",
    }
    if mes_completo:
        return f"Parte mensual de ausencias {meses[date_from.month]} de {date_from.year}"
    return (
        f"Parte mensual de ausencias "
        f"({date_from.strftime('%d/%m/%Y')} – {date_to.strftime('%d/%m/%Y')})"
    )
