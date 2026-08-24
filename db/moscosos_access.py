"""Aceptación de normas de reserva (app moscosos)."""

from __future__ import annotations

from db.connection import get_db


def ensure_moscosos_normas_schema() -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS moscosos_normas_accepted_at TIMESTAMPTZ
                """
            )


def has_accepted_moscosos_normas(*, user_id: int) -> bool:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT moscosos_normas_accepted_at IS NOT NULL AS ok
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
    return bool(row and row.get("ok"))


def accept_moscosos_normas(*, user_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET moscosos_normas_accepted_at = COALESCE(
                    moscosos_normas_accepted_at, now()
                )
                WHERE id = %s
                """,
                (user_id,),
            )
