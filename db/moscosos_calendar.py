"""Calendario de moscosos: lectivos escolares menos zonas de vacaciones y exclusiones admin."""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Iterable

from ausencias.services.stats_calendar import is_holiday
from db.connection import get_db
from db.school_calendar import MES_ES, get_latest_calendar, normalize_other_holidays

BUFFER_SCHOOL_DAYS_DEFAULT = 7
COURSE_EDGE_SCHOOL_DAYS = 7  # día marcado + 6 lectivos siguientes/anteriores
BOOKING_ADVANCE_MONTHS = 3
BOOKING_NEAR_DAYS = 10  # hoy y los 9 días siguientes no se pueden reservar


def ensure_moscosos_calendar_schema() -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS moscosos_calendar_config (
                    id SERIAL PRIMARY KEY,
                    school_calendar_id INTEGER NOT NULL UNIQUE
                        REFERENCES school_calendar(id) ON DELETE CASCADE,
                    buffer_school_days INTEGER NOT NULL DEFAULT 7
                        CHECK (buffer_school_days >= 0 AND buffer_school_days <= 30),
                    extra_excluded_dates JSONB NOT NULL DEFAULT '[]'::jsonb,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_moscosos_calendar_config_cal
                ON moscosos_calendar_config (school_calendar_id)
                """
            )
            cur.execute(
                """
                ALTER TABLE moscosos_calendar_config
                ADD COLUMN IF NOT EXISTS course_start_date DATE
                """
            )
            cur.execute(
                """
                ALTER TABLE moscosos_calendar_config
                ADD COLUMN IF NOT EXISTS course_end_date DATE
                """
            )


def _as_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val).strip()[:10])
    except ValueError:
        return None


def _normalize_date_list(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif not value:
        return []
    else:
        return []
    out: list[str] = []
    for item in raw:
        s = str(item).strip()[:10]
        if s and s not in out:
            out.append(s)
    return sorted(out)


def _row_to_config(row: dict) -> dict:
    return {
        "id": row["id"],
        "school_calendar_id": row["school_calendar_id"],
        "buffer_school_days": int(row["buffer_school_days"]),
        "extra_excluded_dates": _normalize_date_list(row.get("extra_excluded_dates")),
        "course_start_date": _as_date(row.get("course_start_date")),
        "course_end_date": _as_date(row.get("course_end_date")),
        "updated_at": row.get("updated_at"),
    }


def get_config_for_calendar(school_calendar_id: int) -> dict:
    ensure_moscosos_calendar_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, school_calendar_id, buffer_school_days, extra_excluded_dates,
                       course_start_date, course_end_date, updated_at
                FROM moscosos_calendar_config
                WHERE school_calendar_id = %s
                """,
                (school_calendar_id,),
            )
            row = cur.fetchone()
            if row:
                return _row_to_config(row)

            cur.execute(
                """
                SELECT first_date, last_day
                FROM school_calendar
                WHERE id = %s
                """,
                (school_calendar_id,),
            )
            cal_row = cur.fetchone()
            default_start = cal_row["first_date"] if cal_row else None
            default_end = cal_row["last_day"] if cal_row else None

            cur.execute(
                """
                INSERT INTO moscosos_calendar_config (
                    school_calendar_id, course_start_date, course_end_date
                )
                VALUES (%s, %s, %s)
                RETURNING id, school_calendar_id, buffer_school_days, extra_excluded_dates,
                          course_start_date, course_end_date, updated_at
                """,
                (school_calendar_id, default_start, default_end),
            )
            row = cur.fetchone()
    return _row_to_config(row)


def set_course_edge_dates(
    school_calendar_id: int,
    *,
    course_start: date | None,
    course_end: date | None,
) -> None:
    ensure_moscosos_calendar_schema()
    get_config_for_calendar(school_calendar_id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE moscosos_calendar_config
                SET course_start_date = %s,
                    course_end_date = %s,
                    updated_at = now()
                WHERE school_calendar_id = %s
                """,
                (course_start, course_end, school_calendar_id),
            )


def _normalize_school_calendar(cal: dict) -> dict:
    if isinstance(cal.get("other_holidays"), str):
        return {**cal, "other_holidays": normalize_other_holidays(cal["other_holidays"])}
    oh = cal.get("other_holidays")
    if oh is not None and not isinstance(oh, list):
        return {**cal, "other_holidays": normalize_other_holidays(oh)}
    return cal


def touch_moscosos_config(school_calendar_id: int) -> None:
    ensure_moscosos_calendar_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE moscosos_calendar_config
                SET updated_at = now()
                WHERE school_calendar_id = %s
                """,
                (school_calendar_id,),
            )


def recalculate_moscosos_after_school_calendar_change(
    school_calendar_id: int | None = None,
) -> None:
    """
    Tras cambiar el calendario escolar (festivos, vacaciones, etc.):
    - Las zonas de 7 días lectivos se recalculan al consultar (no se guardan en BD).
    - Se limpian exclusiones manuales de moscosos en días que ya no son lectivos.
    """
    cal = get_latest_calendar()
    if not cal:
        return
    cal = _normalize_school_calendar(cal)
    cal_id = int(cal["id"])
    if school_calendar_id is not None and cal_id != int(school_calendar_id):
        return

    cfg = get_config_for_calendar(cal_id)
    buffer_days = int(cfg["buffer_school_days"])

    cleaned_extra: list[str] = []
    for raw in cfg["extra_excluded_dates"]:
        s = str(raw).strip()[:10]
        if not s:
            continue
        try:
            day = date.fromisoformat(s)
        except ValueError:
            continue
        if _is_lective_school_day(day, cal):
            cleaned_extra.append(s)

    if cleaned_extra != cfg["extra_excluded_dates"]:
        set_extra_excluded_dates(cal_id, cleaned_extra)

    touch_moscosos_config(cal_id)


def set_extra_excluded_dates(school_calendar_id: int, dates: list[str]) -> None:
    ensure_moscosos_calendar_schema()
    payload = json.dumps(_normalize_date_list(dates))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO moscosos_calendar_config (school_calendar_id, extra_excluded_dates)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (school_calendar_id) DO UPDATE
                SET extra_excluded_dates = EXCLUDED.extra_excluded_dates,
                    updated_at = now()
                """,
                (school_calendar_id, payload),
            )


def _is_lective_school_day(day: date, cal: dict) -> bool:
    """Día lectivo según calendario escolar (lun–vie y sin festivo/vacaciones)."""
    return day.weekday() < 5 and not is_holiday(day, cal)


def _collect_school_days_before(cal: dict, anchor: date, count: int) -> list[date]:
    """Cuenta hacia atrás ``count`` días lectivos (omite festivos sueltos y vacaciones)."""
    first = _as_date(cal.get("first_date")) or anchor
    found: list[date] = []
    cur = anchor - timedelta(days=1)
    guard = 0
    while len(found) < count and guard < 500:
        guard += 1
        if cur < first:
            break
        if _is_lective_school_day(cur, cal):
            found.append(cur)
        cur -= timedelta(days=1)
    return found


def _collect_school_days_after(cal: dict, anchor: date, count: int) -> list[date]:
    """Cuenta hacia delante ``count`` días lectivos (omite festivos sueltos y vacaciones)."""
    last = _as_date(cal.get("last_day")) or anchor
    found: list[date] = []
    cur = anchor + timedelta(days=1)
    guard = 0
    while len(found) < count and guard < 500:
        guard += 1
        if cur > last:
            break
        if _is_lective_school_day(cur, cal):
            found.append(cur)
        cur += timedelta(days=1)
    return found


def compute_course_edge_excluded_dates(
    cal: dict,
    *,
    course_start: date | None,
    course_end: date | None,
    edge_days: int = COURSE_EDGE_SCHOOL_DAYS,
) -> tuple[set[str], set[str], set[str]]:
    """
    Inicio: día marcado + ``edge_days - 1`` lectivos siguientes.
    Fin: día marcado + ``edge_days - 1`` lectivos anteriores.
    Devuelve (inicio, fin, unión).
    """
    start_zone: set[str] = set()
    end_zone: set[str] = set()
    follow = max(0, edge_days - 1)

    if course_start:
        start_zone.add(course_start.isoformat())
        for d in _collect_school_days_after(cal, course_start, follow):
            start_zone.add(d.isoformat())

    if course_end:
        end_zone.add(course_end.isoformat())
        for d in _collect_school_days_before(cal, course_end, follow):
            end_zone.add(d.isoformat())

    return start_zone, end_zone, start_zone | end_zone


def compute_buffer_excluded_dates(cal: dict, buffer_days: int = BUFFER_SCHOOL_DAYS_DEFAULT) -> set[str]:
    """Siete días lectivos antes/después de Navidad y Semana Santa (por defecto)."""
    out: set[str] = set()
    if buffer_days <= 0:
        return out

    xs = _as_date(cal.get("xmas_start"))
    xe = _as_date(cal.get("xmas_end"))
    es = _as_date(cal.get("easter_start"))
    ee = _as_date(cal.get("easter_end"))

    if xs:
        for d in _collect_school_days_before(cal, xs, buffer_days):
            out.add(d.isoformat())
    if xe:
        for d in _collect_school_days_after(cal, xe, buffer_days):
            out.add(d.isoformat())
    if es:
        for d in _collect_school_days_before(cal, es, buffer_days):
            out.add(d.isoformat())
    if ee:
        for d in _collect_school_days_after(cal, ee, buffer_days):
            out.add(d.isoformat())
    return out


def all_moscosos_excluded_dates(
    cal: dict,
    *,
    extra_excluded: Iterable[str] | None = None,
    buffer_days: int = BUFFER_SCHOOL_DAYS_DEFAULT,
    course_start: date | None = None,
    course_end: date | None = None,
) -> set[str]:
    excluded = compute_buffer_excluded_dates(cal, buffer_days)
    _, _, course_edges = compute_course_edge_excluded_dates(
        cal, course_start=course_start, course_end=course_end
    )
    excluded |= course_edges
    for raw in extra_excluded or ():
        s = str(raw).strip()[:10]
        if s:
            excluded.add(s)
    return excluded


def is_moscosos_eligible(day: date, cal: dict, excluded: set[str]) -> bool:
    """Día lectivo escolar y no excluido del calendario de moscosos."""
    if day.weekday() >= 5:
        return False
    if is_holiday(day, cal):
        return False
    return day.isoformat() not in excluded


def _is_between_course_start_and_classes(d: date, first: date, course_start: date | None) -> bool:
    """Entre inicio de curso escolar y comienzo de clases (moscosos)."""
    if course_start is None:
        return False
    return first <= d < course_start


def _is_between_classes_and_course_end(d: date, last: date, course_end: date | None) -> bool:
    """Entre fin de clases (moscosos) y fin de curso escolar."""
    if course_end is None:
        return False
    return course_end < d <= last


RESERVABLE_TRIMESTER_1 = "reservable_trimester_1"
RESERVABLE_TRIMESTER_2 = "reservable_trimester_2"
RESERVABLE_TRIMESTER_3 = "reservable_trimester_3"


def classify_reservable_trimester(
    d: date,
    cal: dict,
    *,
    course_start: date | None,
    course_end: date | None,
) -> str | None:
    """
    Tramo reservable (solo fechas ya válidas para moscoso):
    1 = comienzo de clases → Navidad
    2 = Navidad → Semana Santa
    3 = Semana Santa → fin de clases
    """
    cs = _as_date(course_start)
    ce = _as_date(course_end)
    if cs is not None and d < cs:
        return None
    if ce is not None and d > ce:
        return None

    xs, xe = _as_date(cal.get("xmas_start")), _as_date(cal.get("xmas_end"))
    es, ee = _as_date(cal.get("easter_start")), _as_date(cal.get("easter_end"))

    if xs is not None and d < xs:
        return RESERVABLE_TRIMESTER_1
    if xe is not None and es is not None and xe < d < es:
        return RESERVABLE_TRIMESTER_2
    if ee is not None and d > ee:
        return RESERVABLE_TRIMESTER_3

    if xs is None and ee is None:
        return RESERVABLE_TRIMESTER_1
    if xs is not None and xe is not None and es is None and d > xe:
        return RESERVABLE_TRIMESTER_2
    if es is not None and ee is not None and xs is None and d > ee:
        return RESERVABLE_TRIMESTER_3
    return None


def get_reservable_trimester(
    d: date,
    cal: dict,
    excluded: set[str],
    *,
    course_start: date | None = None,
    course_end: date | None = None,
) -> str | None:
    """Tramo reservable del día, o None si no se puede reservar moscoso."""
    if not is_moscosos_eligible(d, cal, excluded):
        return None
    return classify_reservable_trimester(
        d, cal, course_start=course_start, course_end=course_end
    )


def add_calendar_months(d: date, months: int) -> date:
    """Suma meses conservando el día o el último del mes destino."""
    month0 = d.month - 1 + months
    year = d.year + month0 // 12
    month = month0 % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last))


def max_booking_date(today: date, course_end: date | None = None) -> date:
    """Último día reservable: hoy + 3 meses, sin pasar del fin de clases."""
    limit = add_calendar_months(today, BOOKING_ADVANCE_MONTHS)
    ce = _as_date(course_end)
    if ce is not None:
        limit = min(limit, ce)
    return limit


def buffer_last_booking_date(today: date) -> date:
    """Último día del bloque de 10 días posteriores (no reservable)."""
    return today + timedelta(days=BOOKING_NEAR_DAYS - 1)


def _first_day_next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


@dataclass(frozen=True)
class MoscososDisplayContext:
    """Contexto precalculado para colorear días del calendario moscosos."""

    cal: dict
    first: date
    last: date
    xs: date | None
    xe: date | None
    es: date | None
    ee: date | None
    other: frozenset[str]
    amber_zone: frozenset[str]
    excluded: frozenset[str]
    cs: date | None
    ce: date | None

    @classmethod
    def build(
        cls,
        cal: dict,
        excluded: set[str],
        *,
        buffer_days: int = BUFFER_SCHOOL_DAYS_DEFAULT,
        course_start: date | None = None,
        course_end: date | None = None,
    ) -> MoscososDisplayContext:
        cal = _normalize_school_calendar(cal)
        cs = _as_date(course_start)
        ce = _as_date(course_end)
        buffer_only = compute_buffer_excluded_dates(cal, buffer_days)
        course_start_only, course_end_only, _ = compute_course_edge_excluded_dates(
            cal, course_start=cs, course_end=ce
        )
        amber_zone = buffer_only | course_start_only | course_end_only
        return cls(
            cal=cal,
            first=cal["first_date"],
            last=cal["last_day"],
            xs=_as_date(cal.get("xmas_start")),
            xe=_as_date(cal.get("xmas_end")),
            es=_as_date(cal.get("easter_start")),
            ee=_as_date(cal.get("easter_end")),
            other=frozenset(cal.get("other_holidays") or []),
            amber_zone=frozenset(amber_zone),
            excluded=frozenset(excluded),
            cs=cs,
            ce=ce,
        )


def moscosos_display_day_kind(d: date, ctx: MoscososDisplayContext) -> str:
    """Tipo de celda admin / reserva (sin reglas de ventana de la app)."""
    iso = d.isoformat()
    if d.weekday() >= 5:
        return "neutral"
    if d < ctx.first or d > ctx.last:
        return "neutral"
    if ctx.xs is not None and ctx.xe is not None and ctx.xs <= d <= ctx.xe:
        return "school_holiday"
    if ctx.es is not None and ctx.ee is not None and ctx.es <= d <= ctx.ee:
        return "school_holiday"
    if iso in ctx.other:
        return "school_holiday"
    if iso in ctx.amber_zone or iso in ctx.excluded:
        return "moscosos_amber"
    if _is_between_course_start_and_classes(d, ctx.first, ctx.cs):
        return "neutral"
    if _is_between_classes_and_course_end(d, ctx.last, ctx.ce):
        return "neutral"
    trim = classify_reservable_trimester(
        d, ctx.cal, course_start=ctx.cs, course_end=ctx.ce
    )
    return trim if trim else "neutral"


def classify_booking_day_kind(
    d: date, today: date, ctx: MoscososDisplayContext
) -> str:
    """Celda del calendario de reserva (ventana + colores moscosos)."""
    if d < today:
        return "booking_past"
    if d <= buffer_last_booking_date(today):
        return "booking_buffer"
    if d > max_booking_date(today, ctx.ce):
        return "booking_too_far"
    return moscosos_display_day_kind(d, ctx)


def _month_calendar_grid(
    month_first: date,
    kind_for_day: Callable[[date], str],
    *,
    reservation_counts: dict[str, int] | None = None,
) -> dict:
    next_m = _first_day_next_month(month_first)
    m_last = next_m - timedelta(days=1)
    days: list[
        tuple[int, int, str]
        | tuple[int, int, str, int]
        | tuple[int, int, str, int, str]
    ] = []
    d = month_first
    while d <= m_last:
        kind = kind_for_day(d)
        if reservation_counts is not None:
            days.append(
                (
                    d.day,
                    d.weekday(),
                    kind,
                    reservation_counts.get(d.isoformat(), 0),
                    d.isoformat(),
                )
            )
        else:
            days.append((d.day, d.weekday(), kind))
        d += timedelta(days=1)
    fw = month_first.weekday()
    return {
        "name": MES_ES[month_first.month],
        "year": month_first.year,
        "first_weekday": fw,
        "leading_cells": [None] * fw,
        "days": days,
    }


def build_moscosos_calendar_months(
    cal: dict,
    excluded: set[str],
    *,
    buffer_days: int = BUFFER_SCHOOL_DAYS_DEFAULT,
    course_start: date | None = None,
    course_end: date | None = None,
) -> list[dict]:
    """Vista anual con tipos de día para plantilla admin (reutiliza MES_ES)."""
    ctx = MoscososDisplayContext.build(
        cal,
        excluded,
        buffer_days=buffer_days,
        course_start=course_start,
        course_end=course_end,
    )
    months: list[dict] = []
    cur = ctx.first.replace(day=1)
    for _ in range(12):
        months.append(
            _month_calendar_grid(cur, lambda d, c=ctx: moscosos_display_day_kind(d, c))
        )
        cur = _first_day_next_month(cur)
    return months


def build_booking_calendar_months(
    today: date,
    cal: dict,
    excluded: set[str],
    *,
    month_count: int = 4,
    buffer_days: int = BUFFER_SCHOOL_DAYS_DEFAULT,
    course_start: date | None = None,
    course_end: date | None = None,
    reservation_counts: dict[str, int] | None = None,
) -> list[dict]:
    """Cuatro meses desde el mes de ``today`` con reglas de ventana de reserva."""
    ctx = MoscososDisplayContext.build(
        cal,
        excluded,
        buffer_days=buffer_days,
        course_start=course_start,
        course_end=course_end,
    )
    months: list[dict] = []
    cur = today.replace(day=1)
    for _ in range(month_count):
        months.append(
            _month_calendar_grid(
                cur,
                lambda d, t=today, c=ctx: classify_booking_day_kind(d, t, c),
                reservation_counts=reservation_counts,
            )
        )
        cur = _first_day_next_month(cur)
    return months


def booking_calendar_visible_range(
    today: date, *, month_count: int = 4
) -> tuple[date, date]:
    """Primer y último día de los meses mostrados en el calendario de reserva."""
    start = today.replace(day=1)
    cur = start
    for _ in range(month_count - 1):
        cur = _first_day_next_month(cur)
    end = _first_day_next_month(cur) - timedelta(days=1)
    return start, end


def moscosos_calendar_bundle() -> dict | None:
    """Calendario escolar + config moscosos + conjunto de exclusiones."""
    cal = get_latest_calendar()
    if not cal:
        return None
    cal = _normalize_school_calendar(cal)
    cfg = get_config_for_calendar(int(cal["id"]))
    buffer_days = int(cfg["buffer_school_days"])
    course_start = cfg.get("course_start_date")
    course_end = cfg.get("course_end_date")
    course_start_zone, course_end_zone, _ = compute_course_edge_excluded_dates(
        cal, course_start=course_start, course_end=course_end
    )
    excluded = all_moscosos_excluded_dates(
        cal,
        extra_excluded=cfg["extra_excluded_dates"],
        buffer_days=buffer_days,
        course_start=course_start,
        course_end=course_end,
    )
    buffer_dates = sorted(compute_buffer_excluded_dates(cal, buffer_days))
    return {
        "calendar": cal,
        "config": cfg,
        "buffer_days": buffer_days,
        "course_edge_days": COURSE_EDGE_SCHOOL_DAYS,
        "course_start_date": course_start,
        "course_end_date": course_end,
        "course_start_dates": sorted(course_start_zone),
        "course_end_dates": sorted(course_end_zone),
        "excluded": excluded,
        "buffer_dates": buffer_dates,
        "extra_dates": cfg["extra_excluded_dates"],
    }
