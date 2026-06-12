"""Calendario escolar (`school_calendar`). Lectura para incidencias y CRUD para administración."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from psycopg.types.json import Json

from db.connection import get_db
from db.groups import get_group_curso
from utils.group_stage import (
    calendar_end_date_key,
    extract_course_num,
    normalize_group_name,
    stage_of,
)

_STAGE_END_COLUMNS = (
    "end_eso",
    "end_fpb1",
    "end_fpb2",
    "end_fpm1",
    "end_fpm2",
    "end_bach1",
    "end_bach2",
)


def ensure_school_calendar_schema() -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            for col in _STAGE_END_COLUMNS:
                cur.execute(
                    f"""
                    ALTER TABLE school_calendar
                    ADD COLUMN IF NOT EXISTS {col} DATE
                    """
                )


def normalize_other_holidays(value: Any) -> list[str]:
    """Convierte JSONB u otros tipos en lista de fechas ISO (YYYY-MM-DD)."""
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, dict):
        return []
    if not value:
        return []
    return [h.strip() for h in str(value).split(",") if h.strip()]


def default_academic_year_start(today: date | None = None) -> date:
    """1 de septiembre del año académico en curso (fallback si no hay fila en BD)."""
    today = today or date.today()
    if today.month >= 9:
        return date(today.year, 9, 1)
    return date(today.year - 1, 9, 1)


def _coerce_calendar_date(val: date | str | None) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def row_to_calendar(row: dict | None) -> dict | None:
    if not row:
        return None
    oh = normalize_other_holidays(row.get("other_holidays"))
    return {
        "id": row["id"],
        "school_year": row["school_year"],
        "first_date": _coerce_calendar_date(row.get("first_date")),
        "last_day": _coerce_calendar_date(row.get("last_day")),
        "xmas_start": _coerce_calendar_date(row.get("xmas_start")),
        "xmas_end": _coerce_calendar_date(row.get("xmas_end")),
        "easter_start": _coerce_calendar_date(row.get("easter_start")),
        "easter_end": _coerce_calendar_date(row.get("easter_end")),
        "other_holidays": oh,
        "updated_at": row.get("updated_at"),
        "end_eso": _coerce_calendar_date(row.get("end_eso")),
        "end_fpb1": _coerce_calendar_date(row.get("end_fpb1")),
        "end_fpb2": _coerce_calendar_date(row.get("end_fpb2")),
        "end_fpm1": _coerce_calendar_date(row.get("end_fpm1")),
        "end_fpm2": _coerce_calendar_date(row.get("end_fpm2")),
        "end_bach1": _coerce_calendar_date(row.get("end_bach1")),
        "end_bach2": _coerce_calendar_date(row.get("end_bach2")),
    }


_CALENDAR_SELECT = """
    SELECT id, school_year, first_date, last_day,
           xmas_start, xmas_end, easter_start, easter_end,
           other_holidays, updated_at,
           end_eso, end_fpb1, end_fpb2, end_fpm1, end_fpm2,
           end_bach1, end_bach2
    FROM school_calendar
"""


def get_primary_calendar_id() -> int | None:
    ensure_school_calendar_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM school_calendar ORDER BY id ASC LIMIT 1")
            row = cur.fetchone()
    return int(row["id"]) if row else None


def _consolidate_duplicates_cursor(cur, primary_id: int) -> None:
    """Fusiona filas duplicadas en la transacción abierta (primary_id = registro canónico)."""
    cur.execute(
        "SELECT id FROM school_calendar WHERE id <> %s ORDER BY id",
        (primary_id,),
    )
    dup_ids = [int(r["id"]) for r in cur.fetchall()]
    for dup_id in dup_ids:
        for col in _STAGE_END_COLUMNS:
            cur.execute(
                f"""
                UPDATE school_calendar AS p
                SET {col} = d.{col}
                FROM school_calendar AS d
                WHERE p.id = %s AND d.id = %s
                  AND p.{col} IS NULL AND d.{col} IS NOT NULL
                """,
                (primary_id, dup_id),
            )
        cur.execute(
            """
            UPDATE moscosos_reservations
            SET school_calendar_id = %s
            WHERE school_calendar_id = %s
            """,
            (primary_id, dup_id),
        )
        cur.execute("DELETE FROM school_calendar WHERE id = %s", (dup_id,))


def consolidate_school_calendar_duplicates() -> int | None:
    """Deja un solo registro (id mínimo) y reasigna referencias de moscosos."""
    primary_id = get_primary_calendar_id()
    if primary_id is None:
        return None
    with get_db() as conn:
        with conn.cursor() as cur:
            _consolidate_duplicates_cursor(cur, primary_id)
    return primary_id


def get_calendar_by_id(cal_id: int) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"{_CALENDAR_SELECT} WHERE id = %s", (cal_id,))
            row = cur.fetchone()
    return row_to_calendar(row)


def get_latest_calendar() -> dict | None:
    """Registro canónico (menor id)."""
    ensure_school_calendar_schema()
    cal_id = get_primary_calendar_id()
    if cal_id is None:
        return None
    return get_calendar_by_id(cal_id)


def get_course_start_iso(today: date | None = None) -> str:
    """Primer día de curso configurado, o 1 sep del año académico actual."""
    cal = get_latest_calendar()
    if cal and cal.get("first_date"):
        fd = cal["first_date"]
        if isinstance(fd, date):
            return fd.isoformat()
        return str(fd)[:10]
    return default_academic_year_start(today).isoformat()


def insert_calendar(
    *,
    school_year: str,
    first_date: date,
    last_day: date,
    xmas_start: date,
    xmas_end: date,
    easter_start: date,
    easter_end: date,
    other_holidays: list[str],
    end_eso: date | None = None,
    end_fpb1: date | None = None,
    end_fpb2: date | None = None,
    end_fpm1: date | None = None,
    end_fpm2: date | None = None,
    end_bach1: date | None = None,
    end_bach2: date | None = None,
) -> None:
    ensure_school_calendar_schema()
    payload = Json(other_holidays)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO school_calendar (
                    school_year, first_date, last_day,
                    xmas_start, xmas_end, easter_start, easter_end,
                    other_holidays,
                    end_eso, end_fpb1, end_fpb2, end_fpm1, end_fpm2,
                    end_bach1, end_bach2
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    school_year,
                    first_date,
                    last_day,
                    xmas_start,
                    xmas_end,
                    easter_start,
                    easter_end,
                    payload,
                    end_eso,
                    end_fpb1,
                    end_fpb2,
                    end_fpm1,
                    end_fpm2,
                    end_bach1,
                    end_bach2,
                ),
            )


def update_calendar_core(
    cal_id: int,
    *,
    school_year: str,
    first_date: date,
    last_day: date,
    xmas_start: date,
    xmas_end: date,
    easter_start: date,
    easter_end: date,
    end_eso: date | None = None,
    end_fpb1: date | None = None,
    end_fpb2: date | None = None,
    end_fpm1: date | None = None,
    end_fpm2: date | None = None,
    end_bach1: date | None = None,
    end_bach2: date | None = None,
) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            for col in _STAGE_END_COLUMNS:
                cur.execute(
                    f"""
                    ALTER TABLE school_calendar
                    ADD COLUMN IF NOT EXISTS {col} DATE
                    """
                )
            cur.execute(
                """
                UPDATE school_calendar
                SET school_year = %s,
                    first_date = %s,
                    last_day = %s,
                    xmas_start = %s,
                    xmas_end = %s,
                    easter_start = %s,
                    easter_end = %s,
                    end_eso = %s,
                    end_fpb1 = %s,
                    end_fpb2 = %s,
                    end_fpm1 = %s,
                    end_fpm2 = %s,
                    end_bach1 = %s,
                    end_bach2 = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    school_year,
                    first_date,
                    last_day,
                    xmas_start,
                    xmas_end,
                    easter_start,
                    easter_end,
                    end_eso,
                    end_fpb1,
                    end_fpb2,
                    end_fpm1,
                    end_fpm2,
                    end_bach1,
                    end_bach2,
                    cal_id,
                ),
            )
            if cur.rowcount != 1:
                raise ValueError(f"No se actualizó el calendario (id={cal_id})")


def save_school_calendar(
    *,
    school_year: str,
    first_date: date,
    last_day: date,
    xmas_start: date,
    xmas_end: date,
    easter_start: date,
    easter_end: date,
    end_eso: date | None = None,
    end_fpb1: date | None = None,
    end_fpb2: date | None = None,
    end_fpm1: date | None = None,
    end_fpm2: date | None = None,
    end_bach1: date | None = None,
    end_bach2: date | None = None,
) -> int:
    """Guarda el calendario escolar en una sola transacción (inserta solo si no existe ninguno)."""
    ensure_school_calendar_schema()
    stage_values = (
        end_eso,
        end_fpb1,
        end_fpb2,
        end_fpm1,
        end_fpm2,
        end_bach1,
        end_bach2,
    )

    with get_db() as conn:
        with conn.cursor() as cur:
            for col in _STAGE_END_COLUMNS:
                cur.execute(
                    f"""
                    ALTER TABLE school_calendar
                    ADD COLUMN IF NOT EXISTS {col} DATE
                    """
                )

            cur.execute("SELECT id FROM school_calendar ORDER BY id ASC LIMIT 1")
            row = cur.fetchone()
            cal_id = int(row["id"]) if row else None

            if cal_id is None:
                cur.execute(
                    """
                    INSERT INTO school_calendar (
                        school_year, first_date, last_day,
                        xmas_start, xmas_end, easter_start, easter_end,
                        other_holidays,
                        end_eso, end_fpb1, end_fpb2, end_fpm1, end_fpm2,
                        end_bach1, end_bach2
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                            %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        school_year,
                        first_date,
                        last_day,
                        xmas_start,
                        xmas_end,
                        easter_start,
                        easter_end,
                        "[]",
                        *stage_values,
                    ),
                )
                cal_id = int(cur.fetchone()["id"])
            else:
                cur.execute(
                    """
                    UPDATE school_calendar
                    SET school_year = %s,
                        first_date = %s,
                        last_day = %s,
                        xmas_start = %s,
                        xmas_end = %s,
                        easter_start = %s,
                        easter_end = %s,
                        end_eso = %s,
                        end_fpb1 = %s,
                        end_fpb2 = %s,
                        end_fpm1 = %s,
                        end_fpm2 = %s,
                        end_bach1 = %s,
                        end_bach2 = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        school_year,
                        first_date,
                        last_day,
                        xmas_start,
                        xmas_end,
                        easter_start,
                        easter_end,
                        *stage_values,
                        cal_id,
                    ),
                )
                if cur.rowcount != 1:
                    raise ValueError(f"No se actualizó el calendario (id={cal_id})")

            _consolidate_duplicates_cursor(cur, cal_id)

    return cal_id


def classes_finished_for_group(
    group_name: str,
    the_date: date,
    cal: dict | None = None,
) -> bool:
    """
    True si las clases del grupo ya han terminado según el calendario escolar.
    Si no hay fecha configurada para esa etapa, devuelve False.
    """
    cal = cal or get_latest_calendar()
    if not cal:
        return False

    grupo = normalize_group_name(group_name)
    if not grupo:
        return False

    curso = get_group_curso(grupo) or get_group_curso(group_name)
    stage = stage_of(grupo=grupo, curso=curso)
    if not stage:
        return False

    course_num = extract_course_num(grupo=grupo, curso=curso, stage=stage)
    end_key = calendar_end_date_key(stage=stage, course_num=course_num)
    if not end_key:
        return False

    end_d = _coerce_calendar_date(cal.get(end_key))
    if end_d is None:
        return False

    return the_date > end_d


def set_other_holidays(cal_id: int, holidays: list[str]) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE school_calendar
                SET other_holidays = %s::jsonb,
                    updated_at = now()
                WHERE id = %s
                """,
                (json.dumps(holidays), cal_id),
            )


MES_ES = (
    "",
    "ENERO",
    "FEBRERO",
    "MARZO",
    "ABRIL",
    "MAYO",
    "JUNIO",
    "JULIO",
    "AGOSTO",
    "SEPTIEMBRE",
    "OCTUBRE",
    "NOVIEMBRE",
    "DICIEMBRE",
)

STAGE_END_LABELS: tuple[tuple[str, str], ...] = (
    ("end_eso", "ESO"),
    ("end_fpb1", "1º FPB"),
    ("end_fpb2", "2º FPB"),
    ("end_fpm1", "1º FPM"),
    ("end_fpm2", "2º FPM"),
    ("end_bach1", "1º Bach"),
    ("end_bach2", "2º Bach"),
)


def stage_end_markers(cal: dict) -> dict[str, str]:
    """Fecha ISO -> etiqueta(s) de fin de clases por etapa."""
    markers: dict[str, str] = {}
    for key, label in STAGE_END_LABELS:
        d = _coerce_calendar_date(cal.get(key))
        if not d:
            continue
        iso = d.isoformat()
        if iso in markers:
            markers[iso] = f"{markers[iso]}, {label}"
        else:
            markers[iso] = label
    return markers


def stage_end_legend_items(cal: dict) -> list[tuple[str, str]]:
    """Lista (etiqueta, fecha dd/mm/yyyy) para la leyenda de la vista anual."""
    items: list[tuple[str, str]] = []
    for key, label in STAGE_END_LABELS:
        d = _coerce_calendar_date(cal.get(key))
        if d:
            items.append((label, d.strftime("%d/%m/%Y")))
    return items


def build_calendar_months(cal: dict) -> list[dict]:
    """Doce meses desde el mes calendario que incluye `first_date` (como en la app de ausencias)."""
    first: date = cal["first_date"]
    last: date = cal["last_day"]
    xs, xe = cal.get("xmas_start"), cal.get("xmas_end")
    es, ee = cal.get("easter_start"), cal.get("easter_end")
    other = set(cal.get("other_holidays") or [])
    stage_markers = stage_end_markers(cal)

    months: list[dict] = []
    cur = first.replace(day=1)

    for _ in range(12):
        year = cur.year
        month = cur.month

        if month == 12:
            next_m = cur.replace(year=year + 1, month=1, day=1)
        else:
            next_m = cur.replace(month=month + 1, day=1)

        m_last = next_m - timedelta(days=1)
        days: list[tuple[int, int, str, str]] = []
        d = cur
        while d <= m_last:
            tip = ""
            iso = d.isoformat()
            if iso in stage_markers:
                kind = "stage_end"
                tip = stage_markers[iso]
            elif d.weekday() >= 5:
                kind = "weekend"
            elif d < first or d > last:
                kind = "out"
            elif xs is not None and xe is not None and xs <= d <= xe:
                kind = "xmas"
            elif es is not None and ee is not None and es <= d <= ee:
                kind = "easter"
            elif iso in other:
                kind = "holiday"
            else:
                kind = "class"

            days.append((d.day, d.weekday(), kind, tip))
            d += timedelta(days=1)

        fw = cur.weekday()
        months.append(
            {
                "name": MES_ES[month],
                "year": year,
                "first_weekday": fw,
                "leading_cells": [None] * fw,
                "days": days,
            }
        )
        cur = next_m

    return months
