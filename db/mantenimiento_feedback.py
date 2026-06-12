"""Avisos del buzón Mantenimiento (tabla propia)."""

from __future__ import annotations

from db.connection import get_db

TABLE = "mantenimiento_feedback"
_schema_ready = False


def _migrate_from_legacy(cur) -> None:
    cur.execute("SELECT to_regclass('public.portal_feedback')")
    if cur.fetchone()["to_regclass"] is None:
        return
    cur.execute(
        f"""
        INSERT INTO {TABLE} (id, user_id, sent_at, tipo, mensaje, read_at, read_by_user_id)
        SELECT id, user_id, sent_at, tipo, mensaje, read_at, read_by_user_id
        FROM portal_feedback
        WHERE buzon = 'mantenimiento'
          AND NOT EXISTS (SELECT 1 FROM {TABLE} LIMIT 1)
        ON CONFLICT (id) DO NOTHING
        """
    )


def ensure_mantenimiento_feedback_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    tipo TEXT NOT NULL CHECK (tipo IN (
                        'mantenimiento_edificio', 'mantenimiento_informatica'
                    )),
                    mensaje TEXT NOT NULL,
                    read_at TIMESTAMPTZ,
                    read_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
                )
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_mantfb_sent_at ON {TABLE} (sent_at DESC)"
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_mantfb_user_id ON {TABLE} (user_id)"
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_mantfb_read_at ON {TABLE} (read_at)"
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS read_notice_dismissed_at TIMESTAMPTZ
                """
            )
            try:
                _migrate_from_legacy(cur)
            except Exception:
                pass
    _schema_ready = True


def insert_feedback(*, user_id: int, tipo: str, mensaje: str) -> int:
    ensure_mantenimiento_feedback_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (user_id, tipo, mensaje)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (user_id, tipo, mensaje),
            )
            return int(cur.fetchone()["id"])


def list_feedback_for_user(*, user_id: int, limit: int = 200) -> list[dict]:
    ensure_mantenimiento_feedback_schema()
    safe_limit = max(1, min(int(limit), 500))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, user_id, sent_at, tipo, mensaje, read_at
                FROM {TABLE}
                WHERE user_id = %s
                ORDER BY sent_at DESC, id DESC
                LIMIT %s
                """,
                (user_id, safe_limit),
            )
            return list(cur.fetchall())


def list_all_feedback(*, limit: int = 500) -> list[dict]:
    ensure_mantenimiento_feedback_schema()
    safe_limit = max(1, min(int(limit), 1000))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT f.id, f.user_id, f.sent_at, f.tipo, f.mensaje,
                       f.read_at, f.read_by_user_id,
                       u.name AS user_name
                FROM {TABLE} f
                LEFT JOIN users u ON u.id = f.user_id
                ORDER BY f.sent_at DESC, f.id DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            return list(cur.fetchall())


def list_read_confirmations_for_author(*, user_id: int, limit: int = 20) -> list[dict]:
    """Mensajes del autor ya marcados como leídos (para avisos en el portal)."""
    ensure_mantenimiento_feedback_schema()
    safe_limit = max(1, min(int(limit), 50))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT f.id, f.read_at,
                       COALESCE(NULLIF(TRIM(r.name), ''), 'Un usuario') AS reader_name
                FROM {TABLE} f
                LEFT JOIN users r ON r.id = f.read_by_user_id
                WHERE f.user_id = %s
                  AND f.read_at IS NOT NULL
                  AND f.read_notice_dismissed_at IS NULL
                ORDER BY f.read_at DESC, f.id DESC
                LIMIT %s
                """,
                (user_id, safe_limit),
            )
            return list(cur.fetchall())


def dismiss_read_notice_for_author(*, feedback_id: int, user_id: int) -> bool:
    """El autor del mensaje cierra el aviso de lectura confirmada en el portal."""
    ensure_mantenimiento_feedback_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET read_notice_dismissed_at = now()
                WHERE id = %s
                  AND user_id = %s
                  AND read_at IS NOT NULL
                  AND read_notice_dismissed_at IS NULL
                RETURNING id
                """,
                (feedback_id, user_id),
            )
            return cur.fetchone() is not None


def mark_feedback_read(*, feedback_id: int, reader_user_id: int) -> bool:
    ensure_mantenimiento_feedback_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET read_at = now(), read_by_user_id = %s
                WHERE id = %s AND read_at IS NULL
                RETURNING id
                """,
                (reader_user_id, feedback_id),
            )
            return cur.fetchone() is not None
