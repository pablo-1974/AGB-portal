"""Rejilla mensual del calendario de actividades extraescolares."""

from __future__ import annotations

from datetime import date, timedelta

from utils.time_madrid import today_madrid
from db.school_calendar import (
    MES_ES,
    default_academic_year_start,
    get_latest_calendar,
    normalize_other_holidays,
)


def parse_month_anchor(value: str | None, *, today: date | None = None) -> date:
    """Primer día del mes ancla (``YYYY-MM``) o el mes actual."""
    today = today or today_madrid()
    if not value:
        return today.replace(day=1)
    raw = str(value).strip()
    if len(raw) >= 7 and raw[4] == "-":
        try:
            year = int(raw[:4])
            month = int(raw[5:7])
            if 1 <= month <= 12:
                return date(year, month, 1)
        except ValueError:
            pass
    return today.replace(day=1)


def _first_day_next_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _as_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val).strip()[:10])
    except ValueError:
        return None


def month_start(d: date | str) -> date:
    fd = _as_date(d)
    if not fd:
        raise ValueError("fecha inválida")
    return fd.replace(day=1)


def last_day_of_month(month_first: date) -> date:
    return _first_day_next_month(month_first.replace(day=1)) - timedelta(days=1)


def academic_year_month_bounds(
    school_cal: dict | None, *, today: date | None = None
) -> tuple[date, date]:
    """Primer y último mes (día 1) del curso según calendario escolar."""
    today = today or today_madrid()
    if school_cal:
        return month_start(school_cal["first_date"]), month_start(school_cal["last_day"])

    start = default_academic_year_start(today)
    start_month = date(start.year, 9, 1)
    if today.month >= 9:
        end_month = date(today.year + 1, 6, 1)
    else:
        end_month = date(today.year, 6, 1)
    if end_month < start_month:
        end_month = date(start_month.year + 1, 6, 1)
    return start_month, end_month


def clamp_month_to_academic(m: date, start_month: date, end_month: date) -> date:
    m = m.replace(day=1)
    if m < start_month:
        return start_month
    if m > end_month:
        return end_month
    return m


def list_academic_month_options(start_month: date, end_month: date) -> list[dict]:
    options: list[dict] = []
    cur = start_month
    while cur <= end_month:
        options.append(
            {
                "value": month_param(cur),
                "label": f"{MES_ES[cur.month].capitalize()} {cur.year}",
            }
        )
        cur = _first_day_next_month(cur)
    return options


def resolve_desde_hasta(
    desde_s: str | None,
    hasta_s: str | None,
    mes_legacy: str | None,
    *,
    today: date,
    start_month: date,
    end_month: date,
) -> tuple[date, date]:
    """Meses seleccionados (inclusive), con valores por defecto del curso lectivo."""
    default_desde = clamp_month_to_academic(today.replace(day=1), start_month, end_month)
    default_hasta = end_month

    if mes_legacy and not desde_s:
        desde_s = mes_legacy

    desde = clamp_month_to_academic(
        parse_month_anchor(desde_s, today=default_desde),
        start_month,
        end_month,
    )
    hasta = clamp_month_to_academic(
        parse_month_anchor(hasta_s, today=default_hasta) if hasta_s else default_hasta,
        start_month,
        end_month,
    )
    if desde > hasta:
        hasta = desde
    return desde, hasta


def visible_date_range_for_months(desde_month: date, hasta_month: date) -> tuple[date, date]:
    start = desde_month.replace(day=1)
    end = last_day_of_month(hasta_month.replace(day=1))
    return start, end


def month_param(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def format_date_es(d: date) -> str:
    return f"{d.day} de {MES_ES[d.month].lower()} de {d.year}"


def format_range_es(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        return f"{MES_ES[start.month].capitalize()} {start.year}"
    if start.year == end.year:
        return (
            f"{MES_ES[start.month].capitalize()} – {MES_ES[end.month].capitalize()} "
            f"de {start.year}"
        )
    return (
        f"{MES_ES[start.month].capitalize()} {start.year} – "
        f"{MES_ES[end.month].capitalize()} {end.year}"
    )


def _day_school_kind(d: date, cal: dict | None) -> str:
    if d.weekday() >= 5:
        return "weekend"
    if not cal:
        return "class"
    first: date = cal["first_date"]
    last: date = cal["last_day"]
    xs, xe = cal.get("xmas_start"), cal.get("xmas_end")
    es, ee = cal.get("easter_start"), cal.get("easter_end")
    other = set(cal.get("other_holidays") or [])
    if d < first or d > last:
        return "out"
    if xs is not None and xe is not None and xs <= d <= xe:
        return "xmas"
    if es is not None and ee is not None and es <= d <= ee:
        return "easter"
    if d.isoformat() in other:
        return "holiday"
    return "class"


def build_extraescolares_calendar_months(
    desde_month: date,
    hasta_month: date,
    *,
    school_cal: dict | None,
    by_date: dict[str, list[dict]],
) -> list[dict]:
    """Rejilla de cada mes entre ``desde_month`` y ``hasta_month`` (inclusive)."""
    months: list[dict] = []
    cur = desde_month.replace(day=1)
    end = hasta_month.replace(day=1)
    while cur <= end:
        next_m = _first_day_next_month(cur)
        m_last = next_m - timedelta(days=1)
        days: list[tuple] = []
        d = cur
        while d <= m_last:
            iso = d.isoformat()
            days.append(
                (
                    d.day,
                    d.weekday(),
                    _day_school_kind(d, school_cal),
                    iso,
                    by_date.get(iso, []),
                )
            )
            d += timedelta(days=1)
        fw = cur.weekday()
        months.append(
            {
                "name": MES_ES[cur.month],
                "year": cur.year,
                "first_weekday": fw,
                "leading_cells": [None] * fw,
                "days": days,
            }
        )
        cur = next_m
    return months


def calendario_filter_url(*, desde: date, hasta: date) -> str:
    return f"/extraescolares/calendario?desde={month_param(desde)}&hasta={month_param(hasta)}"


def school_calendar_for_display() -> dict | None:
    cal = get_latest_calendar()
    if not cal:
        return None
    cal = dict(cal)
    cal["other_holidays"] = normalize_other_holidays(cal.get("other_holidays"))
    return cal
