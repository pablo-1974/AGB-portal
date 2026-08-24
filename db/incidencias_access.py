"""Aceptación de normas de uso (app incidencias)."""

from __future__ import annotations

from db.connection import get_db


def ensure_incidencias_normas_schema() -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS incidencias_normas_accepted_at TIMESTAMPTZ
                """
            )


def has_accepted_incidencias_normas(*, user_id: int) -> bool:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT incidencias_normas_accepted_at IS NOT NULL AS ok
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
    return bool(row and row.get("ok"))


def accept_incidencias_normas(*, user_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET incidencias_normas_accepted_at = COALESCE(
                    incidencias_normas_accepted_at, now()
                )
                WHERE id = %s
                """,
                (user_id,),
            )
