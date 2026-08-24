"""
Parte diario: misma rejilla que la app de consulta (pdf_daily.build_daily_report_data).
Filas = franjas horarias; columnas = PROFESOR, GRUPO, AULA, ASIGN., FIRMAS, GUARDIA.

Baja y excedencia se tratan igual: el titular cuenta ausente por ``leaves`` en los
días del periodo si ese día no está cubierto por sustituto (véase
``teachers_absent_that_day``). No se usa ``users.status`` para distinguirlas aquí.
"""
from __future__ import annotations

from datetime import date

from ausencias.db import list_absences_range, list_leaves, list_schedule_slots_for_weekday
from db.connection import get_db
from db.school_calendar import classes_finished_for_group, get_latest_calendar
from utils.text import normalize_for_sort

HOUR_ROWS: tuple[tuple[str, int], ...] = (
    ("1ª", 0),
    ("2ª", 1),
    ("3ª", 2),
    ("RECREO", 3),
    ("4ª", 4),
    ("5ª", 5),
    ("6ª", 6),
)

RECREO_INDEX = 3
FULL_MASK = (1 << 7) - 1

HEAD = ["HORA", "PROFESOR", "GRUPO", "AULA", "ASIGN.", "FIRMAS", "GUARDIA"]

_WEEKDAYS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def report_title(the_date: date) -> str:
    wd = _WEEKDAYS_ES[the_date.weekday()].capitalize()
    return f"Ausencias del día ({wd} {the_date.strftime('%d/%m/%Y')})"


def pdf_report_title(the_date: date) -> str:
    """Título PDF como en consultas (día de la semana en minúsculas)."""
    wd = _WEEKDAYS_ES[the_date.weekday()]
    return f"Ausencias del día ({wd} {the_date.strftime('%d/%m/%Y')})"


def _is_absent(mask: int, hour_idx: int) -> bool:
    return (mask & (1 << hour_idx)) != 0


def _coerce_date(val: date | str | None) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def _leave_substitute_covers_day(lv: dict, the_date: date) -> bool:
    """Sustituto nombrado y aplicable ese día: el titular de la baja no cuenta ausente por esa baja."""
    if lv.get("substitute_teacher_id") is None:
        return False
    ss = _coerce_date(lv.get("substitute_start_date"))
    if ss is None or ss > the_date:
        return False
    se = _coerce_date(lv.get("substitute_end_date"))
    if se is not None and se < the_date:
        return False
    return True


def _slot_type_upper(row: dict) -> str:
    return str(row.get("slot_type") or "").strip().upper()


def _pick_slot(candidates: list[dict] | None) -> dict | None:
    if not candidates:
        return None
    cls = next((s for s in candidates if _slot_type_upper(s) == "CLASS"), None)
    if cls:
        return cls
    return next((s for s in candidates if _slot_type_upper(s) == "GUARD"), None)


def _pick_absent_slot(
    candidates: list[dict] | None,
    the_date: date,
    school_cal: dict | None,
) -> dict | None:
    """CLASS activa (etapa sin finalizar); si no, guardia (salvo G RECREO).

    Las horas OTHER no salen en el parte diario (sí cuentan en el mensual
    a través de la máscara de ausencia).
    """
    if not candidates:
        return None
    for slot in candidates:
        if _slot_type_upper(slot) != "CLASS":
            continue
        group_name = str(slot.get("group") or "").strip()
        if group_name.upper() == "ED":
            continue
        if classes_finished_for_group(group_name, the_date, school_cal):
            continue
        return slot
    for slot in candidates:
        if _slot_type_upper(slot) != "GUARD":
            continue
        gt = str(slot.get("guard_type") or "").upper()
        if gt.startswith("G RECREO"):
            continue
        return slot
    return None


def _index_slots_by_teacher_hour(rows: list[dict]) -> dict[tuple[int, int], list[dict]]:
    idx: dict[tuple[int, int], list[dict]] = {}
    for r in rows:
        key = (int(r["teacher_id"]), int(r["hour_index"]))
        idx.setdefault(key, []).append(r)
    return idx


def _prof_labels_for_teacher_ids(ids: set[int]) -> dict[int, str]:
    """Texto columna PROFESOR: alias si existe; si no, nombre completo."""
    users = _users_for_teacher_ids(ids)
    return {tid: _display_name(users.get(tid)) for tid in ids}


def _users_for_teacher_ids(ids: set[int]) -> dict[int, dict]:
    if not ids:
        return {}
    id_list = list(ids)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, COALESCE(alias, '') AS alias, active, COALESCE(status, 'activo') AS status
                FROM users
                WHERE id = ANY(%s)
                """,
                (id_list,),
            )
            return {int(r["id"]): dict(r) for r in cur.fetchall()}


def _display_name(u: dict | None) -> str:
    if not u:
        return ""
    alias = str(u.get("alias") or "").strip()
    if alias:
        return alias
    return str(u.get("name") or "").strip()


def teachers_absent_that_day(the_date: date) -> tuple[set[int], dict[int, int]]:
    """Ausentes por tabla ``absences`` y por ``leaves`` raíz; baja y excedencia igual si no hay sustituto."""
    leaves = list_leaves(include_closed=True)

    titular_cubierto_por_sustituto: set[int] = set()
    for lv in leaves:
        if lv.get("is_substitution"):
            continue
        sd = _coerce_date(lv.get("start_date"))
        ed = _coerce_date(lv.get("end_date"))
        if sd is None or sd > the_date:
            continue
        if ed is not None and ed < the_date:
            continue
        if _leave_substitute_covers_day(lv, the_date):
            titular_cubierto_por_sustituto.add(int(lv["teacher_id"]))

    absent_ids: set[int] = set()
    hours_by_teacher: dict[int, int] = {}

    for a in list_absences_range(from_date=the_date, to_date=the_date):
        tid = int(a["teacher_id"])
        if tid in titular_cubierto_por_sustituto:
            continue
        absent_ids.add(tid)
        hours_by_teacher[tid] = hours_by_teacher.get(tid, 0) | int(a.get("hours_mask") or 0)

    # Titular en baja o excedencia: mismo criterio (leave raíz vigente sin sustituto ese día).
    for lv in leaves:
        if lv.get("is_substitution"):
            continue
        sd = _coerce_date(lv.get("start_date"))
        ed = _coerce_date(lv.get("end_date"))
        if sd is None or sd > the_date:
            continue
        if ed is not None and ed < the_date:
            continue
        if _leave_substitute_covers_day(lv, the_date):
            continue
        tid = int(lv["teacher_id"])
        absent_ids.add(tid)
        hours_by_teacher[tid] = hours_by_teacher.get(tid, 0) | FULL_MASK

    return absent_ids, hours_by_teacher


def _leave_future_substitution(teacher_id: int, the_date: date, leaves: list[dict]) -> bool:
    return any(
        int(lv["teacher_id"]) == teacher_id
        and bool(lv.get("is_substitution"))
        and lv.get("start_date") is not None
        and lv["start_date"] > the_date
        for lv in leaves
    )


def _leave_active_non_substitution(teacher_id: int, the_date: date, leaves: list[dict]) -> bool:
    return any(
        int(lv["teacher_id"]) == teacher_id
        and not bool(lv.get("is_substitution"))
        and lv.get("start_date") is not None
        and lv["start_date"] <= the_date
        and (lv.get("end_date") is None or lv["end_date"] >= the_date)
        for lv in leaves
    )


def _crush(xs: list[str]) -> str:
    return "\n".join(x for x in xs if x and str(x).strip())


def build_daily_report_grid(the_date: date) -> tuple[list[str], list[list[str]], list[str]]:
    """
    Devuelve ``(head, rows, ausentes_guardia_recreo)`` como el parte legacy.
    ``ausentes_guardia_recreo``: alias/nombre para el bloque observaciones del PDF.
    """
    weekday_py = the_date.weekday()
    absent_ids, hours_by_teacher = teachers_absent_that_day(the_date)
    prof_labels = _prof_labels_for_teacher_ids(absent_ids)

    slots_flat = list_schedule_slots_for_weekday(day_index=weekday_py)
    idx = _index_slots_by_teacher_hour(slots_flat)
    school_cal = get_latest_calendar()

    leaves = list_leaves(include_closed=True)

    ausentes_gr: list[str] = []
    for tid in absent_ids:
        if not _is_absent(hours_by_teacher.get(tid, 0), RECREO_INDEX):
            continue
        slot = _pick_slot(idx.get((tid, RECREO_INDEX)))
        if not slot or _slot_type_upper(slot) != "GUARD":
            continue
        if not str(slot.get("guard_type") or "").upper().startswith("G RECREO"):
            continue
        label = prof_labels.get(tid, "").strip()
        if label:
            ausentes_gr.append(label)
    ausentes_guardia_recreo = sorted(set(ausentes_gr), key=normalize_for_sort)

    grid_rows: list[list[str]] = []

    for label, hour_idx in HOUR_ROWS:
        if hour_idx == RECREO_INDEX:
            grid_rows.append(["RECREO", "", "", "", "", "", ""])
            continue

        row_prof: list[str] = []
        row_grp: list[str] = []
        row_room: list[str] = []
        row_subj: list[str] = []

        for tid in sorted(absent_ids, key=lambda i: normalize_for_sort(prof_labels.get(i, ""))):
            mask = hours_by_teacher.get(tid, 0)
            if not _is_absent(mask, hour_idx):
                continue

            slot = _pick_absent_slot(idx.get((tid, hour_idx)), the_date, school_cal)
            if not slot:
                continue

            prof_label = prof_labels.get(tid, "")

            if _slot_type_upper(slot) == "CLASS":
                group_name = str(slot.get("group") or "")
                row_prof.append(prof_label)
                row_grp.append(group_name)
                row_room.append(str(slot.get("room") or ""))
                row_subj.append(str(slot.get("subject") or ""))
            else:
                gt = str(slot.get("guard_type") or "").upper()
                if gt.startswith("G RECREO"):
                    continue
                row_prof.append(prof_label)
                row_grp.append("guardia")
                row_room.append("guardia")
                row_subj.append("guardia")

        guard_teacher_ids: set[int] = set()
        for r in slots_flat:
            if int(r["hour_index"]) != hour_idx:
                continue
            if _slot_type_upper(r) != "GUARD":
                continue
            guard_teacher_ids.add(int(r["teacher_id"]))

        guard_aliases: list[str] = []
        guard_users = _users_for_teacher_ids(guard_teacher_ids)
        guard_display_by_id = {tid: _display_name(guard_users.get(tid)) for tid in guard_teacher_ids}

        for tid in sorted(guard_teacher_ids, key=lambda i: normalize_for_sort(guard_display_by_id.get(i, ""))):
            if _is_absent(hours_by_teacher.get(tid, 0), hour_idx):
                continue

            slot = _pick_slot(idx.get((tid, hour_idx)))
            if not slot or _slot_type_upper(slot) != "GUARD":
                continue

            gt = str(slot.get("guard_type") or "").upper()
            if gt.startswith("G RECREO"):
                continue

            u = guard_users.get(tid)
            if not u or int(u.get("active") or 0) != 1:
                continue
            if str(u.get("status") or "activo") != "activo":
                continue

            if _leave_future_substitution(tid, the_date, leaves):
                continue
            if _leave_active_non_substitution(tid, the_date, leaves):
                continue

            guard_aliases.append(_display_name(u))

        # Los cuatro primeros campos se rellenan en el mismo orden (por profesor ausente):
        # no ordenar grupo/aula/asign. por separado o se desalinean respecto al profesor.
        grid_rows.append(
            [
                label,
                _crush(row_prof),
                _crush(row_grp),
                _crush(row_room),
                _crush(row_subj),
                "",
                _crush(sorted(guard_aliases, key=normalize_for_sort)),
            ]
        )

    return HEAD, grid_rows, ausentes_guardia_recreo


def build_daily_report_preview(the_date: date, observaciones: str = "") -> dict:
    head, rows, ausentes_gr = build_daily_report_grid(the_date)
    return {
        "title": report_title(the_date),
        "pdf_title": pdf_report_title(the_date),
        "observaciones": (observaciones or "").strip(),
        "ausentes_guardia_recreo": ausentes_gr,
        "head": head,
        "rows": rows,
    }
