"""Asignación de horas nominales a miembros en el reparto (un grupo por clic)."""

from __future__ import annotations

from db.connection import get_db

TABLE = "reparto_nominal_asignaciones"
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


def ensure_reparto_nominal_asignaciones_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id SERIAL PRIMARY KEY,
                    hora_nominal_id INTEGER NOT NULL,
                    departamento_abrev TEXT NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_reparto_nom_asig_depto
                ON {TABLE} (departamento_abrev)
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_reparto_nom_asig_hn
                ON {TABLE} (departamento_abrev, hora_nominal_id)
                """
            )
            cur.execute(
                """
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a
                  ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass AND i.indisprimary
                """,
                (TABLE,),
            )
            pk_cols = [str(r["attname"]) for r in cur.fetchall()]
            if pk_cols == ["hora_nominal_id"]:
                cur.execute(
                    f"""
                    CREATE TABLE reparto_nominal_asignaciones_new (
                        id SERIAL PRIMARY KEY,
                        hora_nominal_id INTEGER NOT NULL,
                        departamento_abrev TEXT NOT NULL,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    f"""
                    INSERT INTO reparto_nominal_asignaciones_new
                        (hora_nominal_id, departamento_abrev, user_id, created_at)
                    SELECT na.hora_nominal_id, na.departamento_abrev, na.user_id, now()
                    FROM {TABLE} na
                    JOIN reparto_horas_nominales hn ON hn.id = na.hora_nominal_id
                    CROSS JOIN generate_series(
                        1,
                        GREATEST(
                            1,
                            CASE
                                WHEN TRIM(COALESCE(hn.grupos, '')) = '' THEN 1
                                WHEN TRIM(hn.grupos) ~ '^[0-9]+$'
                                    THEN TRIM(hn.grupos)::integer
                                ELSE 1
                            END
                        )
                    ) AS s(n)
                    """
                )
                cur.execute(f"DROP TABLE {TABLE}")
                cur.execute(
                    "ALTER TABLE reparto_nominal_asignaciones_new "
                    "RENAME TO reparto_nominal_asignaciones"
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_reparto_nom_asig_depto
                    ON {TABLE} (departamento_abrev)
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_reparto_nom_asig_hn
                    ON {TABLE} (departamento_abrev, hora_nominal_id)
                    """
                )
    _schema_ready = True


def get_nominal_asignaciones_counts(departamento_abrev: str) -> dict[tuple[int, int], int]:
    """(hora_nominal_id, user_id) → número de grupos asignados."""
    ensure_reparto_nominal_asignaciones_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT hora_nominal_id, user_id, COUNT(*) AS n
                FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                GROUP BY hora_nominal_id, user_id
                """,
                (key,),
            )
            return {
                (int(r["hora_nominal_id"]), int(r["user_id"])): int(r["n"])
                for r in cur.fetchall()
            }


def get_nominal_grupos_asignados_por_columna(departamento_abrev: str) -> dict[int, int]:
    """hora_nominal_id → total de grupos asignados."""
    ensure_reparto_nominal_asignaciones_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT hora_nominal_id, COUNT(*) AS n
                FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                GROUP BY hora_nominal_id
                """,
                (key,),
            )
            return {int(r["hora_nominal_id"]): int(r["n"]) for r in cur.fetchall()}


def add_nominal_asignacion(
    *,
    departamento_abrev: str,
    hora_nominal_id: int,
    user_id: int,
) -> int | None:
    """Añade un grupo de esa hora nominal al profesor. Devuelve id de la fila o None."""
    ensure_reparto_nominal_asignaciones_schema()
    from db.reparto_repartir_config import ensure_reparto_repartir_config_schema
    from db.reparto_pasos import ensure_reparto_pasos_schema, TIPO_NOMINAL

    ensure_reparto_repartir_config_schema()
    ensure_reparto_pasos_schema()
    key = (departamento_abrev or "").strip()
    hn_id = int(hora_nominal_id)
    uid = int(user_id)
    if not key or hn_id <= 0 or uid <= 0:
        return None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, grupos FROM reparto_horas_nominales
                WHERE id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (hn_id, key),
            )
            row = cur.fetchone()
            if not row:
                return None
            slots = _grupos_slots(str(row.get("grupos") or ""))
            cur.execute(
                f"""
                SELECT COUNT(*) AS n FROM {TABLE}
                WHERE hora_nominal_id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (hn_id, key),
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
                INSERT INTO {TABLE} (hora_nominal_id, departamento_abrev, user_id)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (hn_id, key, uid),
            )
            new_id = int(cur.fetchone()["id"])
            cur.execute(
                """
                INSERT INTO reparto_pasos
                    (departamento_abrev, tipo, registro_id, turno_user_id)
                VALUES (%s, %s, %s, %s)
                """,
                (key, TIPO_NOMINAL, new_id, turno_ant),
            )
    return new_id


def delete_nominal_asignacion_by_id(asignacion_id: int) -> bool:
    """Elimina una asignación nominal por id."""
    ensure_reparto_nominal_asignaciones_schema()
    aid = int(asignacion_id)
    if aid <= 0:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (aid,))
            return cur.rowcount > 0


def clear_nominal_asignaciones(departamento_abrev: str) -> bool:
    """Elimina todas las asignaciones nominales del departamento."""
    from db.reparto_pasos import clear_pasos

    ensure_reparto_nominal_asignaciones_schema()
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
    clear_pasos(key)
    return True
