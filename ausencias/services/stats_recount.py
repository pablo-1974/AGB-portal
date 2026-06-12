"""Recuento administrativo ausencias + bajas (legacy stats/recount)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from db.connection import get_db
from db.school_calendar import get_latest_calendar
from utils.text import normalize_for_sort

from ausencias.absence_categories import ABSENCE_CATEGORIES
from ausencias.services.stats_calendar import iter_lective_days, is_holiday

STATS_CAUSA_CODES = tuple(c for c, _ in ABSENCE_CATEGORIES if c != "Z")


def _coerce_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def get_stats_recount(
    *,
    date_from: date,
    date_to: date,
    teacher_id: int | None = None,
    tipo: str = "both",
    categoria: str = "ALL",
) -> list[dict]:
    """
    Agrupa por (profesor, tipo, causa). Excluye Z, sustituciones y profes en excedencia en bajas.
    """
    cal_row = get_latest_calendar()
    if not cal_row:
        return []

    cat_filter = (categoria or "ALL").strip().upper()
    if cat_filter != "ALL" and cat_filter not in STATS_CAUSA_CODES:
        cat_filter = "ALL"

    acc: dict[tuple[int, str, str], int] = defaultdict(int)
    rows_lv: list = []

    with get_db() as conn:
        with conn.cursor() as cur:
            if tipo in ("absences", "both"):
                q = """
                    SELECT teacher_id, date, category
                    FROM absences
                    WHERE date >= %s AND date <= %s
                      AND category IS NOT NULL
                      AND TRIM(category) <> ''
                      AND UPPER(TRIM(category)) <> 'Z'
                """
                params: list = [date_from, date_to]
                if teacher_id is not None:
                    q += " AND teacher_id = %s"
                    params.append(teacher_id)
                if cat_filter != "ALL":
                    q += " AND UPPER(TRIM(category)) = %s"
                    params.append(cat_filter)
                cur.execute(q, params)
                for row in cur.fetchall():
                    d = _coerce_date(row["date"])
                    if d is None:
                        continue
                    if d.weekday() >= 5 or is_holiday(d, cal_row):
                        continue
                    cat = str(row["category"]).strip().upper()[:8] or "?"
                    tid = int(row["teacher_id"])
                    acc[(tid, "Ausencia", cat)] += 1

            if tipo in ("leaves", "both"):
                q = """
                    SELECT l.teacher_id, l.start_date, l.end_date, l.category
                    FROM leaves l
                    JOIN users u ON u.id = l.teacher_id
                    WHERE l.start_date <= %s
                      AND (l.end_date IS NULL OR l.end_date >= %s)
                      AND l.category IS NOT NULL
                      AND TRIM(l.category) <> ''
                      AND UPPER(TRIM(l.category)) <> 'Z'
                      AND COALESCE(l.is_substitution, FALSE) = FALSE
                      AND LOWER(TRIM(COALESCE(NULLIF(TRIM(u.status), ''), 'activo'))) <> 'excedencia'
                """
                params_lv = [date_to, date_from]
                if teacher_id is not None:
                    q += " AND l.teacher_id = %s"
                    params_lv.append(teacher_id)
                if cat_filter != "ALL":
                    q += " AND UPPER(TRIM(l.category)) = %s"
                    params_lv.append(cat_filter)
                cur.execute(q, params_lv)
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
        cat = str(lv["category"]).strip().upper()[:8] or "?"
        tid = int(lv["teacher_id"])
        for _day in iter_lective_days(eff_from, eff_to, cal_row):
            acc[(tid, "Baja", cat)] += 1

    if not acc:
        return []

    teacher_ids = list({k[0] for k in acc})
    name_by_id: dict[int, str] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name FROM users WHERE id = ANY(%s)",
                (teacher_ids,),
            )
            for row in cur.fetchall():
                name_by_id[int(row["id"])] = str(row.get("name") or "")

    out = []
    for (tid, tipo_txt, cat), days in acc.items():
        out.append(
            {
                "teacher": name_by_id.get(tid, f"ID {tid}"),
                "type": tipo_txt,
                "category": cat,
                "days": days,
            }
        )

    out.sort(
        key=lambda r: (
            normalize_for_sort(r["teacher"]),
            r["type"],
            r["category"],
        )
    )
    return out
