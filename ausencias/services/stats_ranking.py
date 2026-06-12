"""Ranking por días de ausencia/baja (legacy stats/ranking)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from db.connection import get_db
from db.school_calendar import get_latest_calendar
from utils.text import normalize_for_sort

from ausencias.services.stats_calendar import iter_lective_days, is_holiday


def _coerce_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def get_stats_ranking(
    *,
    date_from: date,
    date_to: date,
    tipo: str = "both",
) -> list[dict]:
    cal_row = get_latest_calendar()
    if not cal_row:
        return []

    acc: dict[int, int] = defaultdict(int)
    rows_lv: list = []

    with get_db() as conn:
        with conn.cursor() as cur:
            if tipo in ("absences", "both"):
                cur.execute(
                    """
                    SELECT teacher_id, date
                    FROM absences
                    WHERE date >= %s AND date <= %s
                      AND category IS NOT NULL
                      AND TRIM(category) <> ''
                      AND UPPER(TRIM(category)) <> 'Z'
                    """,
                    (date_from, date_to),
                )
                for row in cur.fetchall():
                    d = _coerce_date(row["date"])
                    if d is None:
                        continue
                    if d.weekday() >= 5 or is_holiday(d, cal_row):
                        continue
                    acc[int(row["teacher_id"])] += 1

            if tipo in ("leaves", "both"):
                cur.execute(
                    """
                    SELECT l.teacher_id, l.start_date, l.end_date
                    FROM leaves l
                    JOIN users u ON u.id = l.teacher_id
                    WHERE l.start_date <= %s
                      AND (l.end_date IS NULL OR l.end_date >= %s)
                      AND l.category IS NOT NULL
                      AND TRIM(l.category) <> ''
                      AND UPPER(TRIM(l.category)) <> 'Z'
                      AND COALESCE(l.is_substitution, FALSE) = FALSE
                      AND LOWER(TRIM(COALESCE(NULLIF(TRIM(u.status), ''), 'activo'))) <> 'excedencia'
                    """,
                    (date_to, date_from),
                )
                rows_lv = list(cur.fetchall())

    for lv in rows_lv:
        sf = _coerce_date(lv["start_date"])
        if sf is None:
            continue
        en_raw = lv["end_date"]
        eff_from = max(date_from, sf)
        if en_raw is None:
            eff_to = date_to
        else:
            en = _coerce_date(en_raw)
            if en is None:
                continue
            eff_to = min(en, date_to)
        tid = int(lv["teacher_id"])
        for _day in iter_lective_days(eff_from, eff_to, cal_row):
            acc[tid] += 1

    if not acc:
        return []

    teacher_ids = list(acc.keys())
    name_by_id: dict[int, str] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name FROM users WHERE id = ANY(%s)",
                (teacher_ids,),
            )
            for row in cur.fetchall():
                name_by_id[int(row["id"])] = str(row.get("name") or "")

    rows = [{"teacher": name_by_id.get(tid, f"ID {tid}"), "days": days} for tid, days in acc.items()]
    rows.sort(key=lambda r: (-r["days"], normalize_for_sort(r["teacher"])))
    return rows
