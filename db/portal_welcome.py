"""Aceptación del mensaje de bienvenida del portal (primer acceso)."""

from __future__ import annotations

from db.connection import get_db

_schema_ready = False


def ensure_portal_welcome_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS portal_welcome_accepted_at TIMESTAMPTZ
                """
            )
            # Quienes ya usaron el portal no deben ver «primer acceso».
            cur.execute(
                """
                UPDATE users
                SET portal_welcome_accepted_at = COALESCE(last_login_at, created_at, now())
                WHERE portal_welcome_accepted_at IS NULL
                  AND last_login_at IS NOT NULL
                """
            )
    _schema_ready = True


def has_accepted_portal_welcome(*, user_id: int) -> bool:
    ensure_portal_welcome_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT portal_welcome_accepted_at IS NOT NULL AS ok
                FROM users
                WHERE id = %s
                """,
                (int(user_id),),
            )
            row = cur.fetchone()
    return bool(row and row.get("ok"))


def accept_portal_welcome(*, user_id: int) -> None:
    ensure_portal_welcome_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET portal_welcome_accepted_at = COALESCE(
                    portal_welcome_accepted_at, now()
                )
                WHERE id = %s
                """,
                (int(user_id),),
            )
