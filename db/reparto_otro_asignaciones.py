"""Asignación de conceptos Otros a miembros en el reparto (un grupo por clic)."""

from __future__ import annotations

from db.connection import get_db

TABLE = "reparto_otro_asignaciones"
_schema_ready = False


def _grupos_slots(grupos: str) -> int:
    raw = str(grupos or "").strip().replace(",", ".")
    if not raw:
        return 1
    try:
        g = int(raw)
        return max(1, g)
    except ValueError:
        return 1


def ensure_reparto_otro_asignaciones_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id SERIAL PRIMARY KEY,
                    otro_id INTEGER NOT NULL,
                    departamento_abrev TEXT NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_reparto_otro_asig_depto
                ON {TABLE} (departamento_abrev)
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_reparto_otro_asig_otro
                ON {TABLE} (departamento_abrev, otro_id)
                """
            )
    _schema_ready = True


def add_otro_asignacion(
    *,
    departamento_abrev: str,
    otro_id: int,
    user_id: int,
) -> bool:
    """Añade un grupo de ese concepto Otros al profesor."""
    ensure_reparto_otro_asignaciones_schema()
    key = (departamento_abrev or "").strip()
    o_id = int(otro_id)
    uid = int(user_id)
    if not key or o_id <= 0 or uid <= 0:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, grupos FROM reparto_otros
                WHERE id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (o_id, key),
            )
            row = cur.fetchone()
            if not row:
                return False
            slots = _grupos_slots(str(row.get("grupos") or ""))
            cur.execute(
                f"""
                SELECT COUNT(*) AS n FROM {TABLE}
                WHERE otro_id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (o_id, key),
            )
            used = int(cur.fetchone()["n"])
            if used >= slots:
                return False
            cur.execute(
                f"""
                INSERT INTO {TABLE} (otro_id, departamento_abrev, user_id)
                VALUES (%s, %s, %s)
                """,
                (o_id, key, uid),
            )
    return True


def add_otro_asignacion_and_set_turno(
    *,
    departamento_abrev: str,
    otro_id: int,
    user_id: int,
    turno_user_id: int | None,
) -> int | None:
    """Inserta asignación Otros, registra paso y actualiza turno."""
    ensure_reparto_otro_asignaciones_schema()
    from db.reparto_repartir_config import ensure_reparto_repartir_config_schema
    from db.reparto_pasos import ensure_reparto_pasos_schema, TIPO_OTRO

    ensure_reparto_repartir_config_schema()
    ensure_reparto_pasos_schema()
    key = (departamento_abrev or "").strip()
    o_id = int(otro_id)
    uid = int(user_id)
    if not key or o_id <= 0 or uid <= 0:
        return None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, grupos FROM reparto_otros
                WHERE id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (o_id, key),
            )
            row = cur.fetchone()
            if not row:
                return None
            slots = _grupos_slots(str(row.get("grupos") or ""))
            cur.execute(
                f"""
                SELECT COUNT(*) AS n FROM {TABLE}
                WHERE otro_id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (o_id, key),
            )
            used = int(cur.fetchone()["n"])
            if used >= slots:
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
                INSERT INTO {TABLE} (otro_id, departamento_abrev, user_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (o_id, key, uid),
            )
            new_id = int(cur.fetchone()["id"])
            cur.execute(
                """
                INSERT INTO reparto_pasos
                    (departamento_abrev, tipo, registro_id, turno_user_id)
                VALUES (%s, %s, %s, %s)
                """,
                (key, TIPO_OTRO, new_id, turno_ant),
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


def delete_otro_asignacion_by_id(asignacion_id: int) -> bool:
    """Elimina una asignación Otros por id."""
    ensure_reparto_otro_asignaciones_schema()
    aid = int(asignacion_id)
    if aid <= 0:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (aid,))
            return cur.rowcount > 0


def clear_otro_asignaciones(departamento_abrev: str) -> bool:
    """Elimina todas las asignaciones Otros del departamento."""
    ensure_reparto_otro_asignaciones_schema()
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
    return True
