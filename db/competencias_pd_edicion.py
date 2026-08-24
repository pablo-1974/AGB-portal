"""Bloqueo de edición de porcentajes PD para jefes de departamento."""

from __future__ import annotations

from db.connection import get_db

TABLE = "competencias_pd_edicion"

_schema_ready = False


def ensure_competencias_pd_edicion_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id SMALLINT PRIMARY KEY DEFAULT 1,
                    bloquear_jefes BOOLEAN NOT NULL DEFAULT FALSE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT {TABLE}_one_row CHECK (id = 1)
                )
                """
            )
            cur.execute(
                f"""
                INSERT INTO {TABLE} (id)
                VALUES (1)
                ON CONFLICT (id) DO NOTHING
                """
            )
    _schema_ready = True


def pd_jefes_bloqueados() -> bool:
    ensure_competencias_pd_edicion_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT bloquear_jefes FROM {TABLE} WHERE id = 1")
            row = cur.fetchone()
    if not row:
        return False
    return bool(row.get("bloquear_jefes"))


def set_pd_jefes_bloqueados(bloquear: bool) -> bool:
    ensure_competencias_pd_edicion_schema()
    val = bool(bloquear)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (id, bloquear_jefes, updated_at)
                VALUES (1, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    bloquear_jefes = EXCLUDED.bloquear_jefes,
                    updated_at = NOW()
                """,
                (val,),
            )
    return val
