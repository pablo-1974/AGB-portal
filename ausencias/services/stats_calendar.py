"""Auxiliares de calendario escolar para estadísticas (misma lógica que la app legacy SQLAlchemy)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable


def _as_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val).strip()[:10])
    except ValueError:
        return None


def is_holiday(day: date, cal: dict) -> bool:
    """True si el día no es lectivo según el calendario escolar configurado."""
    first = _as_date(cal.get("first_date"))
    last = _as_date(cal.get("last_day"))
    if first is not None and day < first:
        return True
    if last is not None and day > last:
        return True

    xs, xe = _as_date(cal.get("xmas_start")), _as_date(cal.get("xmas_end"))
    if xs is not None and xe is not None and xs <= day <= xe:
        return True

    es, ee = _as_date(cal.get("easter_start")), _as_date(cal.get("easter_end"))
    if es is not None and ee is not None and es <= day <= ee:
        return True

    ds = day.isoformat()
    for h in cal.get("other_holidays") or []:
        if str(h).strip()[:10] == ds:
            return True

    return False


def iter_lective_days(start: date, end: date, cal: dict) -> Iterable[date]:
    """Días lectivos reales entre dos fechas (lun–vie, sin festivos de calendario)."""
    cur = start
    while cur <= end:
        if cur.weekday() < 5 and not is_holiday(cur, cal):
            yield cur
        cur += timedelta(days=1)
