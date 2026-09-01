"""Historial de pasos del reparto para deshacer (nominales, carga, otros, saltar turno)."""

from __future__ import annotations

from db.connection import get_db

TABLE = "reparto_pasos"
_schema_ready = False

TIPO_NOMINAL = "nominal"
TIPO_CARGA = "carga"
TIPO_OTRO = "otro"
TIPO_SALTAR = "saltar"


def ensure_reparto_pasos_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id SERIAL PRIMARY KEY,
                    departamento_abrev TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    registro_id INTEGER,
                    turno_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_reparto_pasos_depto_id
                ON {TABLE} (departamento_abrev, id DESC)
                """
            )
    _schema_ready = True


def count_pasos(departamento_abrev: str) -> int:
    ensure_reparto_pasos_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return 0
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) AS n FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (key,),
            )
            return int(cur.fetchone()["n"])


def push_paso(
    *,
    departamento_abrev: str,
    tipo: str,
    registro_id: int | None,
    turno_user_id: int | None,
) -> None:
    ensure_reparto_pasos_schema()
    key = (departamento_abrev or "").strip()
    if not key or tipo not in (
        TIPO_NOMINAL,
        TIPO_CARGA,
        TIPO_OTRO,
        TIPO_SALTAR,
    ):
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE}
                    (departamento_abrev, tipo, registro_id, turno_user_id)
                VALUES (%s, %s, %s, %s)
                """,
                (key, tipo, registro_id, turno_user_id),
            )


def clear_pasos(departamento_abrev: str) -> None:
    ensure_reparto_pasos_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (key,),
            )


def clear_pasos_tipos(departamento_abrev: str, tipos: tuple[str, ...]) -> None:
    ensure_reparto_pasos_schema()
    key = (departamento_abrev or "").strip()
    if not key or not tipos:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                  AND tipo = ANY(%s)
                """,
                (key, list(tipos)),
            )


def get_ultimo_paso(departamento_abrev: str) -> dict | None:
    """Devuelve el último paso sin eliminarlo."""
    ensure_reparto_pasos_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, tipo, registro_id, turno_user_id
                FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                ORDER BY id DESC
                LIMIT 1
                """,
                (key,),
            )
            row = cur.fetchone()
            if not row:
                return None
            tid = row.get("turno_user_id")
            reg = row.get("registro_id")
            return {
                "id": int(row["id"]),
                "tipo": str(row["tipo"]),
                "registro_id": int(reg) if reg is not None else None,
                "turno_user_id": int(tid) if tid is not None else None,
            }


def delete_paso(paso_id: int) -> None:
    ensure_reparto_pasos_schema()
    pid = int(paso_id)
    if pid <= 0:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (pid,))


def pop_paso(departamento_abrev: str) -> dict | None:
    """Elimina el último paso y devuelve sus datos, o None si no hay pasos."""
    paso = get_ultimo_paso(departamento_abrev)
    if not paso:
        return None
    delete_paso(int(paso["id"]))
    return paso
