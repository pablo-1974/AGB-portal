from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Iterable
from urllib.parse import parse_qs, unquote_plus, urlparse

from db.connection import get_db
from db.school_calendar import default_academic_year_start, get_latest_calendar
from reservas.calendar import is_school_day


ROOMS = (
    "Informática A",
    "Informática B",
    "Informática C",
    "Aula Multimedia",
    "Biblioteca",
)

RESERVA_SLOTS = tuple(s for s in ("1ª", "2ª", "3ª", "4ª", "5ª", "6ª"))


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text.strip())


def resolve_reservation_room(value: str | None) -> str:
    """Nombre de aula canónico (ROOMS) desde query ?room=."""
    raw = _nfc(unquote_plus((value or "")).replace("+", " "))
    if not raw:
        return ""
    if raw in ROOMS:
        return raw
    by_norm = {r.casefold(): r for r in ROOMS}
    hit = by_norm.get(raw.casefold())
    if hit:
        return hit
    compact = re.sub(r"\s+", "", raw.casefold())
    for r in ROOMS:
        if re.sub(r"\s+", "", r.casefold()) == compact:
            return r
    return ""


def resolve_reservation_date(value: str | None) -> str:
    """Fecha ISO (YYYY-MM-DD) desde query ?reservation_date=."""
    raw = _nfc(unquote_plus((value or "")).replace("+", " "))
    if not raw:
        return ""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", raw)
    if not m:
        return ""
    candidate = m.group(1)
    try:
        date.fromisoformat(candidate)
    except ValueError:
        return ""
    return candidate


def resolve_reservation_slot(value: str | None) -> str:
    """Franja canónica (RESERVA_SLOTS) desde query ?slot=."""
    raw = _nfc(unquote_plus((value or "")))
    if not raw:
        return ""
    if raw in RESERVA_SLOTS:
        return raw
    by_norm = {s.casefold(): s for s in RESERVA_SLOTS}
    hit = by_norm.get(raw.casefold())
    if hit:
        return hit
    m = re.fullmatch(r"(\d)\s*([ªaº.]?)", raw, re.IGNORECASE)
    if m:
        cand = f"{m.group(1)}ª"
        if cand in RESERVA_SLOTS:
            return cand
    return ""


def parse_reservar_prefill(
    request,
    reservation_date: str | None = None,
    room: str | None = None,
    slot: str | None = None,
) -> tuple[str, str, str]:
    """Fecha, aula y franja desde query string (cuadrantes → reservar)."""
    date_v = ""
    room_v = ""
    slot_v = ""
    if request is not None:
        qs = parse_qs(urlparse(str(request.url)).query, keep_blank_values=False)
        date_v = (qs.get("reservation_date") or [""])[0]
        room_v = (qs.get("room") or [""])[0]
        slot_v = (qs.get("slot") or [""])[0]
    if reservation_date is not None and str(reservation_date).strip():
        date_v = str(reservation_date).strip()
    if room is not None and str(room).strip():
        room_v = str(room).strip()
    if slot is not None and str(slot).strip():
        slot_v = str(slot).strip()

    prefill_date = resolve_reservation_date(date_v)
    prefill_room = resolve_reservation_room(room_v)
    prefill_slot = resolve_reservation_slot(slot_v)
    if request is not None:
        qs = parse_qs(urlparse(str(request.url)).query, keep_blank_values=False)
        if not prefill_date:
            prefill_date = resolve_reservation_date((qs.get("reservation_date") or [""])[0])
        if not prefill_room:
            prefill_room = resolve_reservation_room((qs.get("room") or [""])[0])
        if not prefill_slot:
            prefill_slot = resolve_reservation_slot((qs.get("slot") or [""])[0])
    return prefill_date, prefill_room, prefill_slot


def ensure_reservas_schema() -> None:
    """Crea tablas/índices de reservas si no existen."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS room_reservations (
                    id SERIAL PRIMARY KEY,
                    grupo TEXT NOT NULL,
                    room TEXT NOT NULL,
                    reservation_date DATE NOT NULL,
                    slot TEXT NOT NULL,
                    reserved_for_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    reserved_for_name TEXT NOT NULL,
                    created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    notes TEXT
                )
                """
            )
            cur.execute("ALTER TABLE room_reservations ADD COLUMN IF NOT EXISTS grupo TEXT")
            cur.execute("UPDATE room_reservations SET grupo = 'SIN_GRUPO' WHERE grupo IS NULL")
            cur.execute("ALTER TABLE room_reservations ALTER COLUMN grupo SET NOT NULL")
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_room_reservations_room_day_slot
                ON room_reservations (room, reservation_date, slot)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_room_reservations_day
                ON room_reservations (reservation_date)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_room_reservations_for_user
                ON room_reservations (reserved_for_user_id, reservation_date)
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS room_reservations_recurring (
                    id SERIAL PRIMARY KEY,
                    grupo TEXT NOT NULL,
                    room TEXT NOT NULL,
                    weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
                    slot TEXT NOT NULL,
                    start_date DATE NOT NULL,
                    end_date DATE NULL,
                    reserved_for_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    reserved_for_name TEXT NOT NULL,
                    created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    notes TEXT
                )
                """
            )
            cur.execute("ALTER TABLE room_reservations_recurring ADD COLUMN IF NOT EXISTS grupo TEXT")
            cur.execute("UPDATE room_reservations_recurring SET grupo = 'SIN_GRUPO' WHERE grupo IS NULL")
            cur.execute("ALTER TABLE room_reservations_recurring ALTER COLUMN grupo SET NOT NULL")
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_room_reservations_recurring_range
                ON room_reservations_recurring (start_date, end_date)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_room_reservations_recurring_for_user
                ON room_reservations_recurring (reserved_for_user_id)
                """
            )


def _iso(d: date) -> str:
    return d.isoformat()


def get_week_bounds(containing_day: date) -> tuple[date, date]:
    # Lunes..Viernes (cuadrante escolar)
    monday = containing_day - timedelta(days=containing_day.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def course_bounds_for_week(week_monday: date) -> tuple[date, date]:
    """Límites de curso para navegación −/+ en cuadrantes."""
    cal = get_latest_calendar()
    if cal and cal.get("first_date") and cal.get("last_day"):
        first, last = cal["first_date"], cal["last_day"]
        week_end = week_monday + timedelta(days=4)
        if week_end >= first and week_monday <= last:
            return first, last
    start = default_academic_year_start(week_monday)
    return start, date(start.year + 1, 6, 30)


def build_week_nav(
    monday: date,
    *,
    school_first: date | None = None,
    school_last: date | None = None,
) -> dict[str, str | None]:
    """Lunes anterior/siguiente (ISO) para botones − / + en cuadrantes."""
    prev_mon = monday - timedelta(days=7)
    next_mon = monday + timedelta(days=7)
    week_end = monday + timedelta(days=4)
    # Semana mostrada fuera del calendario cargado: permitir ±7 (p. ej. curso 26/27 en BD y vista en mayo).
    if school_first is None or school_last is None:
        return {"prev": prev_mon.isoformat(), "next": next_mon.isoformat()}
    if week_end < school_first or monday > school_last:
        return {"prev": prev_mon.isoformat(), "next": next_mon.isoformat()}
    prev = (
        prev_mon.isoformat()
        if prev_mon + timedelta(days=4) >= school_first
        else None
    )
    nxt = next_mon.isoformat() if next_mon <= school_last else None
    return {"prev": prev, "next": nxt}


def list_reservations_range(*, start: date, end: date) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    grupo,
                    room,
                    reservation_date,
                    slot,
                    reserved_for_user_id,
                    reserved_for_name,
                    created_by_user_id,
                    created_at,
                    notes
                FROM room_reservations
                WHERE reservation_date >= %s AND reservation_date <= %s
                ORDER BY reservation_date, room, slot, id
                """,
                (start, end),
            )
            return list(cur.fetchall())


def get_reservation_by_id(*, reservation_id: int) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id, grupo, room, reservation_date, slot,
                    reserved_for_user_id, reserved_for_name,
                    created_by_user_id, created_at, notes
                FROM room_reservations
                WHERE id = %s
                """,
                (reservation_id,),
            )
            return cur.fetchone()


def list_reservations_filtered(
    *,
    user_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    room: str | None = None,
    grupo: str | None = None,
    reserved_for_user_id: int | None = None,
) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            clauses: list[str] = []
            params: list = []

            if user_id is not None:
                clauses.append("reserved_for_user_id = %s")
                params.append(user_id)
            if start is not None:
                clauses.append("reservation_date >= %s")
                params.append(start)
            if end is not None:
                clauses.append("reservation_date <= %s")
                params.append(end)
            if room:
                clauses.append("room = %s")
                params.append(room)
            if grupo:
                clauses.append("grupo = %s")
                params.append(grupo)
            if reserved_for_user_id is not None:
                clauses.append("reserved_for_user_id = %s")
                params.append(reserved_for_user_id)

            where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            cur.execute(
                f"""
                SELECT
                    id, grupo, room, reservation_date, slot,
                    reserved_for_user_id, reserved_for_name,
                    created_by_user_id, created_at, notes
                FROM room_reservations
                {where_sql}
                ORDER BY reservation_date DESC, slot DESC, id DESC
                """,
                tuple(params),
            )
            return list(cur.fetchall())


def create_reservation(
    *,
    grupo: str,
    room: str,
    reservation_date: date,
    slot: str,
    reserved_for_user_id: int,
    reserved_for_name: str,
    created_by_user_id: int,
    notes: str | None = None,
) -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO room_reservations (
                    grupo, room, reservation_date, slot,
                    reserved_for_user_id, reserved_for_name,
                    created_by_user_id, notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    grupo,
                    room,
                    reservation_date,
                    slot,
                    reserved_for_user_id,
                    reserved_for_name,
                    created_by_user_id,
                    notes,
                ),
            )
            row = cur.fetchone()
            return int(row["id"])


def delete_reservation(*, reservation_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM room_reservations WHERE id = %s", (reservation_id,))


def delete_reservations_range(*, start: date, end: date, rooms: Iterable[str] | None = None) -> int:
    rooms_list = list(rooms or [])
    with get_db() as conn:
        with conn.cursor() as cur:
            if rooms_list:
                cur.execute(
                    """
                    DELETE FROM room_reservations
                    WHERE reservation_date >= %s AND reservation_date <= %s
                      AND room = ANY(%s)
                    RETURNING id
                    """,
                    (start, end, rooms_list),
                )
            else:
                cur.execute(
                    """
                    DELETE FROM room_reservations
                    WHERE reservation_date >= %s AND reservation_date <= %s
                    RETURNING id
                    """,
                    (start, end),
                )
            rows = cur.fetchall()
            return len(rows)


def list_recurring() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    grupo,
                    room,
                    weekday,
                    slot,
                    start_date,
                    end_date,
                    reserved_for_user_id,
                    reserved_for_name,
                    created_by_user_id,
                    created_at,
                    notes
                FROM room_reservations_recurring
                ORDER BY room, weekday, slot, id
                """
            )
            return list(cur.fetchall())


def list_recurring_for_range(*, start: date, end: date) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    grupo,
                    room,
                    weekday,
                    slot,
                    start_date,
                    end_date,
                    reserved_for_user_id,
                    reserved_for_name,
                    created_by_user_id,
                    created_at,
                    notes
                FROM room_reservations_recurring
                WHERE start_date <= %s
                  AND (end_date IS NULL OR end_date >= %s)
                ORDER BY room, weekday, slot, id
                """,
                (end, start),
            )
            return list(cur.fetchall())


def recurring_applies_on(rec: dict, d: date) -> bool:
    if rec["weekday"] != d.weekday():
        return False
    if d < rec["start_date"]:
        return False
    if rec["end_date"] is not None and d > rec["end_date"]:
        return False
    return True


def has_conflict_puntual_or_recurring(*, room: str, d: date, slot: str) -> bool:
    # puntual exacta
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM room_reservations
                WHERE room = %s AND reservation_date = %s AND slot = %s
                LIMIT 1
                """,
                (room, d, slot),
            )
            if cur.fetchone():
                return True

            cur.execute(
                """
                SELECT 1
                FROM room_reservations_recurring
                WHERE room = %s
                  AND slot = %s
                  AND weekday = %s
                  AND start_date <= %s
                  AND (end_date IS NULL OR end_date >= %s)
                LIMIT 1
                """,
                (room, slot, d.weekday(), d, d),
            )
            return cur.fetchone() is not None


def user_has_reservation_for_slot(
    *,
    user_id: int,
    room: str,
    d: date,
    slot: str,
) -> bool:
    """El usuario tiene reserva puntual o recurrente para aula, fecha y franja."""
    ensure_reservas_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM room_reservations
                WHERE reserved_for_user_id = %s
                  AND room = %s
                  AND reservation_date = %s
                  AND slot = %s
                LIMIT 1
                """,
                (int(user_id), room, d, slot),
            )
            if cur.fetchone():
                return True
            cur.execute(
                """
                SELECT 1
                FROM room_reservations_recurring
                WHERE reserved_for_user_id = %s
                  AND room = %s
                  AND slot = %s
                  AND weekday = %s
                  AND start_date <= %s
                  AND (end_date IS NULL OR end_date >= %s)
                LIMIT 1
                """,
                (int(user_id), room, slot, d.weekday(), d, d),
            )
            return cur.fetchone() is not None


def get_user_other_room_same_slot(
    *,
    reserved_for_user_id: int,
    d: date,
    slot: str,
    exclude_room: str,
) -> dict | None:
    """Otra aula ya reservada por el mismo usuario en la misma fecha y franja."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT room, reserved_for_name
                FROM room_reservations
                WHERE reserved_for_user_id = %s
                  AND reservation_date = %s
                  AND slot = %s
                  AND room <> %s
                LIMIT 1
                """,
                (reserved_for_user_id, d, slot, exclude_room),
            )
            row = cur.fetchone()
            if row:
                return row

            cur.execute(
                """
                SELECT room, reserved_for_name
                FROM room_reservations_recurring
                WHERE reserved_for_user_id = %s
                  AND slot = %s
                  AND weekday = %s
                  AND room <> %s
                  AND start_date <= %s
                  AND (end_date IS NULL OR end_date >= %s)
                LIMIT 1
                """,
                (
                    reserved_for_user_id,
                    slot,
                    d.weekday(),
                    exclude_room,
                    d,
                    d,
                ),
            )
            return cur.fetchone()


def user_has_double_room_in_recurring_range(
    *,
    reserved_for_user_id: int,
    weekday: int,
    slot: str,
    exclude_room: str,
    start_date: date,
    end_date: date | None,
) -> dict | None:
    """Conflicto de doble aula para una reserva recurrente nueva."""
    range_end = end_date if end_date is not None else (start_date + timedelta(days=365))
    if range_end < start_date:
        return None

    offset = (weekday - start_date.weekday()) % 7
    d = start_date + timedelta(days=offset)
    while d <= range_end:
        if is_school_day(d):
            other = get_user_other_room_same_slot(
                reserved_for_user_id=reserved_for_user_id,
                d=d,
                slot=slot,
                exclude_room=exclude_room,
            )
            if other:
                return {"room": other["room"], "reservation_date": d}
        d += timedelta(days=7)
    return None


def get_conflict_holder(*, room: str, d: date, slot: str) -> dict | None:
    """Devuelve quién ocupa el aula/franja (puntual o recurrente) si hay conflicto."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    reserved_for_user_id,
                    reserved_for_name,
                    FALSE AS is_recurring
                FROM room_reservations
                WHERE room = %s AND reservation_date = %s AND slot = %s
                LIMIT 1
                """,
                (room, d, slot),
            )
            row = cur.fetchone()
            if row:
                return row

            cur.execute(
                """
                SELECT
                    reserved_for_user_id,
                    reserved_for_name,
                    TRUE AS is_recurring
                FROM room_reservations_recurring
                WHERE room = %s
                  AND slot = %s
                  AND weekday = %s
                  AND start_date <= %s
                  AND (end_date IS NULL OR end_date >= %s)
                LIMIT 1
                """,
                (room, slot, d.weekday(), d, d),
            )
            return cur.fetchone()


def has_conflict_for_new_recurring(
    *,
    room: str,
    weekday: int,
    slot: str,
    start_date: date,
    end_date: date | None,
) -> bool:
    range_end = end_date if end_date is not None else (start_date + timedelta(days=365))
    if range_end < start_date:
        return False

    # Solo comprobamos fechas candidatas reales (mismo weekday + día lectivo).
    offset = (weekday - start_date.weekday()) % 7
    first_candidate = start_date + timedelta(days=offset)
    candidate_days: list[date] = []
    d = first_candidate
    while d <= range_end:
        if is_school_day(d):
            candidate_days.append(d)
        d += timedelta(days=7)

    # Si no hay ningún día lectivo aplicable, no hay conflicto operativo.
    if not candidate_days:
        return False

    with get_db() as conn:
        with conn.cursor() as cur:
            # conflicto con otra recurrente solapada misma aula/franja/día
            cur.execute(
                """
                SELECT start_date, end_date
                FROM room_reservations_recurring
                WHERE room = %s
                  AND slot = %s
                  AND weekday = %s
                  AND start_date <= %s
                  AND (end_date IS NULL OR end_date >= %s)
                """,
                (room, slot, weekday, range_end, start_date),
            )
            recurring_rows = cur.fetchall()
            for rec in recurring_rows:
                rec_start = rec["start_date"]
                rec_end = rec["end_date"]
                for cand in candidate_days:
                    if cand >= rec_start and (rec_end is None or cand <= rec_end):
                        return True

            # conflicto con puntuales del mismo weekday dentro del rango
            cur.execute(
                """
                SELECT 1
                FROM room_reservations
                WHERE room = %s
                  AND slot = %s
                  AND reservation_date = ANY(%s)
                LIMIT 1
                """,
                (room, slot, candidate_days),
            )
            if cur.fetchone():
                return True
    return False


def create_recurring(
    *,
    grupo: str,
    room: str,
    weekday: int,
    slot: str,
    start_date: date,
    end_date: date | None,
    reserved_for_user_id: int,
    reserved_for_name: str,
    created_by_user_id: int,
    notes: str | None = None,
) -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO room_reservations_recurring (
                    grupo, room, weekday, slot, start_date, end_date,
                    reserved_for_user_id, reserved_for_name,
                    created_by_user_id, notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    grupo,
                    room,
                    weekday,
                    slot,
                    start_date,
                    end_date,
                    reserved_for_user_id,
                    reserved_for_name,
                    created_by_user_id,
                    notes,
                ),
            )
            row = cur.fetchone()
            return int(row["id"])


def delete_recurring(*, recurring_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM room_reservations_recurring WHERE id = %s", (recurring_id,))
