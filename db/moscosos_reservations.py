"""Reservas de días de moscoso (máx. 2 por día; 2 por usuario/curso en trimestres distintos)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from psycopg import errors as pg_errors

from db.connection import get_db

MAX_RESERVATIONS_PER_DAY = 2
MAX_RESERVATIONS_PER_USER_PER_COURSE = 2


@dataclass(frozen=True)
class MoscososReservation:
    id: int
    reservation_date: date
    trimester: int
    slot: int
    created_at: object
    documentation_sent_at: object | None = None

    @property
    def has_documentation_sent(self) -> bool:
        return self.documentation_sent_at is not None


def _row_to_reservation(row) -> MoscososReservation:
    return MoscososReservation(
        id=int(row["id"]),
        reservation_date=row["reservation_date"],
        trimester=int(row["trimester"]),
        slot=int(row["slot"]),
        created_at=row["created_at"],
        documentation_sent_at=row["documentation_sent_at"],
    )


_RESERVATION_SELECT = """
    SELECT id, reservation_date, trimester, slot, created_at, documentation_sent_at
    FROM moscosos_reservations
"""


def ensure_moscosos_reservations_schema() -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS moscosos_reservations (
                    id SERIAL PRIMARY KEY,
                    school_calendar_id INTEGER NOT NULL
                        REFERENCES school_calendar(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL
                        REFERENCES users(id) ON DELETE CASCADE,
                    reservation_date DATE NOT NULL,
                    trimester SMALLINT NOT NULL
                        CHECK (trimester >= 1 AND trimester <= 3),
                    slot SMALLINT NOT NULL
                        CHECK (slot >= 1 AND slot <= 2),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    UNIQUE (school_calendar_id, reservation_date, slot),
                    UNIQUE (school_calendar_id, user_id, reservation_date)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_moscosos_reservations_cal_date
                ON moscosos_reservations (school_calendar_id, reservation_date)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_moscosos_reservations_user
                ON moscosos_reservations (school_calendar_id, user_id)
                """
            )
            cur.execute(
                """
                ALTER TABLE moscosos_reservations
                ADD COLUMN IF NOT EXISTS documentation_sent_at TIMESTAMPTZ
                """
            )
            cur.execute(
                """
                ALTER TABLE moscosos_reservations
                ADD COLUMN IF NOT EXISTS documentation_director_notice_dismissed_at TIMESTAMPTZ
                """
            )


def reservation_counts_between(
    *,
    school_calendar_id: int,
    date_from: date,
    date_to: date,
) -> dict[str, int]:
    """Mapa ISO fecha → número de reservas (0–2) en el rango."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT reservation_date, COUNT(*)::int AS n
                FROM moscosos_reservations
                WHERE school_calendar_id = %s
                  AND reservation_date >= %s
                  AND reservation_date <= %s
                GROUP BY reservation_date
                """,
                (school_calendar_id, date_from, date_to),
            )
            rows = cur.fetchall()
    out: dict[str, int] = {}
    for r in rows:
        d = r["reservation_date"]
        iso = d.isoformat() if hasattr(d, "isoformat") else str(d)
        out[iso] = int(r["n"])
    return out


def count_reservations_on_day(*, school_calendar_id: int, reservation_date: date) -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int AS n
                FROM moscosos_reservations
                WHERE school_calendar_id = %s AND reservation_date = %s
                """,
                (school_calendar_id, reservation_date),
            )
            row = cur.fetchone()
    return int(row["n"]) if row else 0


def get_user_reservation(
    *, reservation_id: int, user_id: int
) -> MoscososReservation | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {_RESERVATION_SELECT}
                WHERE id = %s AND user_id = %s
                """,
                (reservation_id, user_id),
            )
            row = cur.fetchone()
    if not row:
        return None
    return _row_to_reservation(row)


def list_user_reservations(
    *, school_calendar_id: int, user_id: int
) -> list[MoscososReservation]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {_RESERVATION_SELECT}
                WHERE school_calendar_id = %s AND user_id = %s
                ORDER BY reservation_date
                """,
                (school_calendar_id, user_id),
            )
            rows = cur.fetchall()
    return [_row_to_reservation(r) for r in rows]


def create_reservation(
    *,
    school_calendar_id: int,
    user_id: int,
    reservation_date: date,
    trimester: int,
) -> MoscososReservation | None:
    """
    Crea reserva en la primera plaza libre del día.
    Devuelve None si el día ya tiene dos reservas (plazas ocupadas).
    """
    for slot in (1, 2):
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO moscosos_reservations (
                            school_calendar_id, user_id, reservation_date, trimester, slot
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id, reservation_date, trimester, slot, created_at,
                                  documentation_sent_at
                        """,
                        (
                            school_calendar_id,
                            user_id,
                            reservation_date,
                            trimester,
                            slot,
                        ),
                    )
                    row = cur.fetchone()
            return _row_to_reservation(row)
        except pg_errors.UniqueViolation:
            continue
    return None


def delete_reservation(*, reservation_id: int, user_id: int) -> bool:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM moscosos_reservations
                WHERE id = %s AND user_id = %s
                """,
                (reservation_id, user_id),
            )
            return cur.rowcount > 0


def mark_documentation_sent(*, reservation_id: int, user_id: int) -> bool:
    """Registra el envío del Anexo I; la reserva deja de ser anulable."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE moscosos_reservations
                SET documentation_sent_at = COALESCE(documentation_sent_at, now())
                WHERE id = %s AND user_id = %s
                """,
                (reservation_id, user_id),
            )
            return cur.rowcount > 0


def list_documentation_portal_notices_for_director(*, limit: int = 20) -> list[dict]:
    """Reservas con documentación enviada pendiente de aviso OK por el director."""
    ensure_moscosos_reservations_schema()
    safe_limit = max(1, min(int(limit), 50))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT r.id, r.reservation_date, r.documentation_sent_at,
                       u.id AS user_id,
                       COALESCE(NULLIF(TRIM(u.alias), ''), NULLIF(TRIM(u.name), ''), 'Un profesor')
                           AS sender_label
                FROM moscosos_reservations r
                JOIN users u ON u.id = r.user_id
                WHERE r.documentation_sent_at IS NOT NULL
                  AND r.documentation_director_notice_dismissed_at IS NULL
                ORDER BY r.documentation_sent_at DESC, r.id DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            return list(cur.fetchall())


def dismiss_documentation_portal_notice(*, reservation_id: int) -> bool:
    ensure_moscosos_reservations_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE moscosos_reservations
                SET documentation_director_notice_dismissed_at = now()
                WHERE id = %s
                  AND documentation_sent_at IS NOT NULL
                  AND documentation_director_notice_dismissed_at IS NULL
                RETURNING id
                """,
                (int(reservation_id),),
            )
            return cur.fetchone() is not None


def list_reservations_cuadro(
    *,
    school_calendar_id: int,
    date_from: date,
    date_to: date,
    user_id: int | None = None,
) -> list[dict]:
    """Reservas del curso con datos de profesor (cuadro general)."""
    sql = """
        SELECT r.id, r.reservation_date, r.trimester, r.slot,
               r.documentation_sent_at,
               u.id AS user_id, u.name AS user_name, u.alias AS user_alias
        FROM moscosos_reservations r
        JOIN users u ON u.id = r.user_id
        WHERE r.school_calendar_id = %s
          AND r.reservation_date >= %s
          AND r.reservation_date <= %s
    """
    params: list = [school_calendar_id, date_from, date_to]
    if user_id is not None:
        sql += " AND r.user_id = %s"
        params.append(user_id)
    sql += " ORDER BY r.reservation_date, r.slot"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = list(cur.fetchall())
    out: list[dict] = []
    for r in rows:
        name = (r.get("user_name") or "").strip()
        alias = (r.get("user_alias") or "").strip()
        doc_at = r.get("documentation_sent_at")
        out.append(
            {
                "id": int(r["id"]),
                "reservation_date": r["reservation_date"],
                "date_display": None,  # filled in router
                "trimester": int(r["trimester"]),
                "slot": int(r["slot"]),
                "user_id": int(r["user_id"]),
                "user_name": name,
                "user_alias": alias,
                "marker_label": alias or name,
                "doc_sent": doc_at is not None,
            }
        )
    return out


def _reservation_date_iso(d: object) -> str:
    """Clave YYYY-MM-DD coherente con el calendario (date o datetime de BD)."""
    if isinstance(d, date):
        return d.isoformat()
    if hasattr(d, "date") and callable(getattr(d, "date", None)):
        try:
            return d.date().isoformat()  # type: ignore[union-attr]
        except (AttributeError, TypeError, ValueError):
            pass
    s = str(d).strip()
    if "T" in s:
        s = s.split("T", 1)[0]
    if " " in s:
        s = s.split(" ", 1)[0]
    return s[:10]


def reservation_counts_by_user(*, school_calendar_id: int) -> dict[int, int]:
    """Número de reservas de moscoso por usuario en el curso escolar."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, COUNT(*)::int AS n
                FROM moscosos_reservations
                WHERE school_calendar_id = %s
                GROUP BY user_id
                """,
                (school_calendar_id,),
            )
            rows = cur.fetchall()
    return {int(r["user_id"]): int(r["n"]) for r in rows}


def reservations_by_date_for_cuadro(rows: list[dict]) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    for row in rows:
        iso = _reservation_date_iso(row["reservation_date"])
        by.setdefault(iso, []).append(row)
    for iso in by:
        by[iso].sort(key=lambda x: x["slot"])
    return by


def cancel_user_reservation(
    *, reservation_id: int, user_id: int, today: date
) -> bool:
    """
    Anula una reserva propia si el día no ha pasado y no se ha enviado documentación.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM moscosos_reservations
                WHERE id = %s
                  AND user_id = %s
                  AND reservation_date >= %s
                  AND documentation_sent_at IS NULL
                """,
                (reservation_id, user_id, today),
            )
            return cur.rowcount > 0
