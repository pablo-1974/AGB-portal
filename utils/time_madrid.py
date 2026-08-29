"""Zona horaria Europe/Madrid para reloj del portal, displays y plazos."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ_MADRID = ZoneInfo("Europe/Madrid")
TZ_UTC = ZoneInfo("UTC")


def now_madrid() -> datetime:
    """Instante actual en hora de Madrid (aware)."""
    return datetime.now(TZ_MADRID)


def today_madrid() -> date:
    """Fecha civil de hoy en Madrid."""
    return now_madrid().date()


def as_madrid(value: datetime | date | None) -> datetime | None:
    """Convierte un datetime (UTC/naive) a Europe/Madrid.

    - Aware → astimezone(Madrid)
    - Naive → se asume UTC (típico de Neon/TIMESTAMPTZ sin tzinfo)
    - date → medianoche Madrid de ese día
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=TZ_UTC)
        return value.astimezone(TZ_MADRID)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=TZ_MADRID)
    return None


def format_madrid(
    value: datetime | date | None,
    fmt: str = "%d/%m/%Y %H:%M",
    *,
    empty: str = "—",
) -> str:
    """Formatea un timestamp en hora de Madrid."""
    if value is None:
        return empty
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.strftime(fmt) if "%H" not in fmt else value.strftime("%d/%m/%Y")
    dt = as_madrid(value) if isinstance(value, datetime) else None
    if dt is None:
        return empty
    return dt.strftime(fmt)


def madrid_date(value: datetime | date | None) -> date | None:
    """Fecha civil en Madrid a partir de un datetime/date de BD."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = as_madrid(value)
        return dt.date() if dt else None
    if isinstance(value, date):
        return value
    return None
