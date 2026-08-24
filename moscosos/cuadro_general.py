"""Vista Cuadro general (meses y profesores)."""

from __future__ import annotations

from datetime import date

from db.moscosos_calendar import (
    MoscososDisplayContext,
    _first_day_next_month,
    _month_calendar_grid,
    classify_booking_day_kind,
)
from db.school_calendar import MES_ES


def iter_school_months(first: date, last: date) -> list[date]:
    """Primer día de cada mes entre las fechas del calendario escolar."""
    months: list[date] = []
    cur = first.replace(day=1)
    end = last.replace(day=1)
    while cur <= end:
        months.append(cur)
        cur = _first_day_next_month(cur)
    return months


def month_option_value(month_first: date) -> str:
    return f"{month_first.year:04d}-{month_first.month:02d}"


def parse_month_param(raw: str | None, *, default: date) -> date:
    if not raw:
        return default.replace(day=1)
    try:
        y, m = raw.strip().split("-", 1)
        return date(int(y), int(m), 1)
    except (ValueError, TypeError):
        return default.replace(day=1)


def default_month_first(
    *, school_first: date, school_last: date, today: date
) -> date:
    cur = today.replace(day=1)
    if cur < school_first.replace(day=1):
        return school_first.replace(day=1)
    if cur > school_last.replace(day=1):
        return school_last.replace(day=1)
    return cur


def build_month_options(
    *,
    school_first: date,
    school_last: date,
    selected: date,
) -> list[dict]:
    opts: list[dict] = []
    for month_first in iter_school_months(school_first, school_last):
        opts.append(
            {
                "value": month_option_value(month_first),
                "label": f"{MES_ES[month_first.month]} {month_first.year}",
                "selected": month_first.year == selected.year
                and month_first.month == selected.month,
            }
        )
    return opts


def build_month_nav(
    *,
    school_first: date,
    school_last: date,
    current: date,
) -> dict[str, str | None]:
    """Mes anterior/siguiente del curso (valor YYYY-MM) para botones − / +."""
    months = iter_school_months(school_first, school_last)
    cur = current.replace(day=1)
    idx = next(
        (
            i
            for i, m in enumerate(months)
            if m.year == cur.year and m.month == cur.month
        ),
        None,
    )
    if idx is None:
        return {"prev": None, "next": None}
    prev = month_option_value(months[idx - 1]) if idx > 0 else None
    next_ = (
        month_option_value(months[idx + 1]) if idx < len(months) - 1 else None
    )
    return {"prev": prev, "next": next_}


def enrich_month_with_reservations(
    month_grid: dict,
    *,
    month_first: date,
    reservations_by_date: dict[str, list[dict]],
) -> dict:
    days_out = []
    for day in month_grid["days"]:
        if len(day) >= 5:
            d_num, wd, kind, _slots, iso = day[0], day[1], day[2], day[3], day[4]
        elif len(day) == 3:
            d_num, wd, kind = day[0], day[1], day[2]
            iso = date(month_first.year, month_first.month, d_num).isoformat()
        else:
            continue
        res = reservations_by_date.get(iso, [])
        days_out.append((d_num, wd, kind, iso, res))
    return {**month_grid, "days": days_out}


def build_cuadro_month(
    *,
    month_first: date,
    today: date,
    cal: dict,
    excluded: set[str],
    buffer_days: int,
    course_start: date | None,
    course_end: date | None,
    reservations_by_date: dict[str, list[dict]],
) -> dict:
    ctx = MoscososDisplayContext.build(
        cal,
        excluded,
        buffer_days=buffer_days,
        course_start=course_start,
        course_end=course_end,
    )
    grid = _month_calendar_grid(
        month_first,
        lambda d, t=today, c=ctx: classify_booking_day_kind(d, t, c),
        reservation_counts=None,
    )
    return enrich_month_with_reservations(
        grid, month_first=month_first, reservations_by_date=reservations_by_date
    )


def build_month_days_detail(
    month_grid: dict,
    *,
    format_date_es,
    trimester_label_for,
) -> dict[str, dict]:
    """Datos por ISO para el panel al pulsar un día del mes."""
    out: dict[str, dict] = {}
    for tup in month_grid.get("days") or []:
        if len(tup) != 5:
            continue
        d_num, _wd, _kind, iso, reservations = tup
        if not isinstance(iso, str) or len(iso) < 10:
            continue
        d = date.fromisoformat(iso[:10])
        rows = []
        for r in reservations or []:
            trim = int(r.get("trimester") or 0)
            alias = (r.get("user_alias") or "").strip()
            name = (r.get("user_name") or "").strip()
            rows.append(
                {
                    "id": int(r.get("id") or 0),
                    "user_alias": alias,
                    "user_name": name,
                    "marker_label": (r.get("marker_label") or alias or name),
                    "doc_sent": bool(r.get("doc_sent")),
                    "trimester_label": trimester_label_for(trim),
                }
            )
        out[iso] = {
            "iso": iso,
            "day_num": d_num,
            "label": format_date_es(d),
            "reservations": rows,
        }
    return out


def attach_day_details_to_month(
    month_grid: dict, month_days_detail: dict[str, dict]
) -> dict:
    """Añade el objeto de detalle (6.º elemento) a cada celda del mes."""
    days_out = []
    for tup in month_grid.get("days") or []:
        if len(tup) != 5:
            continue
        iso = tup[3]
        detail = month_days_detail.get(
            iso,
            {
                "iso": iso,
                "day_num": tup[0],
                "label": iso,
                "reservations": list(tup[4] or []),
            },
        )
        days_out.append((*tup, detail))
    return {**month_grid, "days": days_out}


def build_resumen_curso(
    *,
    all_users: list[dict],
    counts_by_user: dict[int, int],
) -> dict[str, list[dict]]:
    """Tres listas: dos reservas, una reserva, ninguna (curso escolar)."""
    two: list[dict] = []
    one: list[dict] = []
    none: list[dict] = []
    for u in all_users:
        n = counts_by_user.get(int(u["id"]), 0)
        alias = (u.get("alias") or "").strip()
        row = {
            "id": int(u["id"]),
            "name": u.get("name") or "",
            "alias": alias,
            "count": n,
        }
        if n >= 2:
            two.append(row)
        elif n == 1:
            one.append(row)
        else:
            none.append(row)
    key_alias = lambda r: (r.get("alias") or r.get("name") or "").casefold()
    two.sort(key=key_alias)
    one.sort(key=key_alias)
    none.sort(key=key_alias)
    return {"two": two, "one": one, "none": none}


def build_resumen_table_rows(resumen_cols: dict[str, list[dict]]) -> list[dict]:
    """Filas alineadas para una única tabla de tres columnas (alias por celda)."""
    two_aliases = [r["alias"] for r in resumen_cols.get("two") or []]
    one_aliases = [r["alias"] for r in resumen_cols.get("one") or []]
    none_aliases = [r["alias"] for r in resumen_cols.get("none") or []]
    n = max(len(two_aliases), len(one_aliases), len(none_aliases))
    rows: list[dict] = []
    for i in range(n):
        rows.append(
            {
                "two": two_aliases[i] if i < len(two_aliases) else "",
                "one": one_aliases[i] if i < len(one_aliases) else "",
                "none": none_aliases[i] if i < len(none_aliases) else "",
            }
        )
    return rows


def parse_date_param(raw: str | None, *, default: date) -> date:
    if not raw:
        return default
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return default
