"""Caché de informes de competencias (payload JSON precalculado)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Json

from db.connection import get_db
from utils.time_madrid import as_madrid, now_madrid

TABLE = "competencias_informes_cache"
_schema_ready = False


def ensure_informes_cache_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    ambito TEXT NOT NULL,
                    sel TEXT NOT NULL,
                    vista TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (ambito, sel, vista)
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_cic_calculated
                ON {TABLE} (calculated_at DESC)
                """
            )
    _schema_ready = True


def get_informe_cache(
    *, ambito: str, sel: str, vista: str
) -> tuple[dict[str, Any] | None, datetime | None]:
    ensure_informes_cache_schema()
    a = (ambito or "").strip().lower()
    s = (sel or "").strip()
    v = (vista or "").strip().lower()
    if not a or not s or not v:
        return None, None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT payload, calculated_at
                FROM {TABLE}
                WHERE ambito = %s AND sel = %s AND vista = %s
                """,
                (a, s, v),
            )
            row = cur.fetchone()
    if not row:
        return None, None
    payload = row.get("payload")
    if isinstance(payload, str):
        import json

        payload = json.loads(payload)
    if not isinstance(payload, dict):
        return None, None
    return payload, as_madrid(row.get("calculated_at"))


def save_informe_cache(
    *,
    ambito: str,
    sel: str,
    vista: str,
    payload: dict[str, Any],
) -> datetime:
    ensure_informes_cache_schema()
    a = (ambito or "").strip().lower()
    s = (sel or "").strip()
    v = (vista or "").strip().lower()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (ambito, sel, vista, payload, calculated_at)
                VALUES (%s, %s, %s, %s::jsonb, NOW())
                ON CONFLICT (ambito, sel, vista) DO UPDATE
                SET payload = EXCLUDED.payload,
                    calculated_at = EXCLUDED.calculated_at
                RETURNING calculated_at
                """,
                (a, s, v, Json(payload)),
            )
            row = cur.fetchone()
    raw = row["calculated_at"] if row else now_madrid()
    return as_madrid(raw) or now_madrid()


def clear_informes_cache() -> None:
    ensure_informes_cache_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE}")


def latest_informes_cache_at() -> datetime | None:
    ensure_informes_cache_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT MAX(calculated_at) AS t FROM {TABLE}")
            row = cur.fetchone()
    return as_madrid((row or {}).get("t"))


def list_informe_cache_sels(*, ambito: str, vista: str) -> list[str]:
    """Sels con caché para un ámbito/vista (orden de BD; el caller ordena)."""
    ensure_informes_cache_schema()
    a = (ambito or "").strip().lower()
    v = (vista or "").strip().lower()
    if not a or not v:
        return []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT sel
                FROM {TABLE}
                WHERE ambito = %s AND vista = %s
                ORDER BY sel
                """,
                (a, v),
            )
            rows = cur.fetchall() or []
    return [str(r.get("sel") or "").strip() for r in rows if r.get("sel")]
