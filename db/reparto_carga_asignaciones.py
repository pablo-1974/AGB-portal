"""Asignaciones de carga docente en el reparto (grupos elegidos por profesor)."""

from __future__ import annotations

from db.connection import get_db

TABLE = "reparto_carga_asignaciones"
_schema_ready = False


def ensure_reparto_carga_asignaciones_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id SERIAL PRIMARY KEY,
                    carga_id INTEGER NOT NULL,
                    departamento_abrev TEXT NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_reparto_carga_asig_depto
                ON {TABLE} (departamento_abrev, carga_id)
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_reparto_carga_asig_user
                ON {TABLE} (departamento_abrev, user_id)
                """
            )
    _schema_ready = True


def get_carga_asignaciones_counts(departamento_abrev: str) -> dict[tuple[int, int], int]:
    """(carga_id, user_id) → número de grupos elegidos."""
    ensure_reparto_carga_asignaciones_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT carga_id, user_id, COUNT(*) AS n
                FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                GROUP BY carga_id, user_id
                """,
                (key,),
            )
            return {
                (int(r["carga_id"]), int(r["user_id"])): int(r["n"])
                for r in cur.fetchall()
            }


def get_carga_grupos_asignados_por_columna(departamento_abrev: str) -> dict[int, int]:
    """carga_id → total de grupos asignados (todos los profesores)."""
    ensure_reparto_carga_asignaciones_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT carga_id, COUNT(*) AS n
                FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                GROUP BY carga_id
                """,
                (key,),
            )
            return {int(r["carga_id"]): int(r["n"]) for r in cur.fetchall()}


def add_carga_asignacion(
    *,
    departamento_abrev: str,
    carga_id: int,
    user_id: int,
) -> bool:
    """Añade un grupo elegido de esa asignatura para el profesor."""
    ensure_reparto_carga_asignaciones_schema()
    key = (departamento_abrev or "").strip()
    cid = int(carga_id)
    uid = int(user_id)
    if not key or cid <= 0 or uid <= 0:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM reparto_carga_docente
                WHERE id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (cid, key),
            )
            if not cur.fetchone():
                return False
            cur.execute(
                f"""
                INSERT INTO {TABLE} (carga_id, departamento_abrev, user_id)
                VALUES (%s, %s, %s)
                """,
                (cid, key, uid),
            )
    return True


def delete_carga_asignacion_by_id(asignacion_id: int) -> bool:
    """Elimina una asignación de carga por id."""
    ensure_reparto_carga_asignaciones_schema()
    aid = int(asignacion_id)
    if aid <= 0:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (aid,))
            return cur.rowcount > 0


def clear_carga_asignaciones(departamento_abrev: str) -> bool:
    """Elimina todas las elecciones de carga docente del departamento."""
    from db.reparto_pasos import clear_pasos_tipos, TIPO_CARGA, TIPO_SALTAR

    ensure_reparto_carga_asignaciones_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (key,),
            )
    clear_pasos_tipos(key, (TIPO_CARGA, TIPO_SALTAR))
    return True


def add_carga_asignacion_and_set_turno(
    *,
    departamento_abrev: str,
    carga_id: int,
    user_id: int,
    turno_user_id: int | None,
) -> int | None:
    """Inserta asignación, registra paso y actualiza turno. Devuelve id de la fila."""
    ensure_reparto_carga_asignaciones_schema()
    from db.reparto_repartir_config import ensure_reparto_repartir_config_schema
    from db.reparto_pasos import ensure_reparto_pasos_schema, TIPO_CARGA

    ensure_reparto_repartir_config_schema()
    ensure_reparto_pasos_schema()
    key = (departamento_abrev or "").strip()
    cid = int(carga_id)
    uid = int(user_id)
    if not key or cid <= 0 or uid <= 0:
        return None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM reparto_carga_docente
                WHERE id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (cid, key),
            )
            if not cur.fetchone():
                return None
            cur.execute(
                f"""
                SELECT turno_user_id FROM reparto_repartir_config
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (key,),
            )
            cfg = cur.fetchone()
            turno_ant = cfg.get("turno_user_id") if cfg else None
            turno_ant = int(turno_ant) if turno_ant is not None else None
            cur.execute(
                f"""
                INSERT INTO {TABLE} (carga_id, departamento_abrev, user_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (cid, key, uid),
            )
            new_id = int(cur.fetchone()["id"])
            cur.execute(
                """
                INSERT INTO reparto_pasos
                    (departamento_abrev, tipo, registro_id, turno_user_id)
                VALUES (%s, %s, %s, %s)
                """,
                (key, TIPO_CARGA, new_id, turno_ant),
            )
            cur.execute(
                """
                UPDATE reparto_repartir_config
                SET turno_user_id = %s, updated_at = now()
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (turno_user_id, key),
            )
    return new_id
