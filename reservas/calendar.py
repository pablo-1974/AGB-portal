from __future__ import annotations

from datetime import date

from db.school_calendar import get_latest_calendar


def is_school_day(d: date) -> bool:
    """
    Día lectivo según el calendario escolar configurado.
    Reglas:
    - Lunes..Viernes
    - Dentro de first_date..last_day
    - Excluye rangos xmas/easter si están definidos
    - Excluye other_holidays (lista de YYYY-MM-DD)
    """
    if d.weekday() >= 5:
        return False

    cal = get_latest_calendar()
    if not cal:
        # Sin calendario, comportamiento conservador: permitir solo lunes-viernes.
        return True

    first = cal["first_date"]
    last = cal["last_day"]
    if d < first or d > last:
        return False

    xs, xe = cal.get("xmas_start"), cal.get("xmas_end")
    if xs is not None and xe is not None and xs <= d <= xe:
        return False

    es, ee = cal.get("easter_start"), cal.get("easter_end")
    if es is not None and ee is not None and es <= d <= ee:
        return False

    if d.isoformat() in (cal.get("other_holidays") or []):
        return False

    return True

