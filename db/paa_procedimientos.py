"""Procedimientos PAA (sanción: suspensión del derecho de asistencia al centro)."""

from __future__ import annotations

from datetime import date

from db.connection import get_db

TABLE = "paa_procedimientos"
_schema_ready = False


def ensure_paa_procedimientos_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id              SERIAL PRIMARY KEY,
                    student_id      INTEGER REFERENCES students(id) ON DELETE SET NULL,
                    alumno          TEXT NOT NULL,
                    grupo           TEXT NOT NULL,
                    fecha_inicio    DATE NOT NULL,
                    fecha_final     DATE NOT NULL,
                    dias_lectivos   INTEGER NOT NULL CHECK (dias_lectivos >= 0),
                    created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                    notice_id       INTEGER
                        REFERENCES portal_published_notices(id) ON DELETE SET NULL,
                    CONSTRAINT paa_fechas_ok CHECK (fecha_inicio <= fecha_final)
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_paa_fecha_inicio
                ON {TABLE} (fecha_inicio DESC)
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_paa_grupo_alumno
                ON {TABLE} (grupo, alumno)
                """
            )
    _schema_ready = True


def _student_id_for(*, grupo: str, alumno: str) -> int | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id FROM students
                WHERE grupo = %s AND alumno = %s
                """,
                ((grupo or "").strip(), (alumno or "").strip()),
            )
            row = cur.fetchone()
            return int(row["id"]) if row else None


def create_paa_procedimiento(
    *,
    alumno: str,
    grupo: str,
    fecha_inicio: date,
    fecha_final: date,
    dias_lectivos: int,
    created_by: int | None,
    notice_id: int | None = None,
) -> int:
    ensure_paa_procedimientos_schema()
    alumno_n = (alumno or "").strip()
    grupo_n = (grupo or "").strip()
    if not alumno_n or not grupo_n:
        raise ValueError("Alumno y grupo son obligatorios")
    if fecha_inicio > fecha_final:
        raise ValueError("La fecha inicial no puede ser posterior a la final")
    if int(dias_lectivos) < 0:
        raise ValueError("Los días lectivos no pueden ser negativos")

    student_id = _student_id_for(grupo=grupo_n, alumno=alumno_n)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    student_id, alumno, grupo,
                    fecha_inicio, fecha_final, dias_lectivos,
                    created_by, notice_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    student_id,
                    alumno_n,
                    grupo_n,
                    fecha_inicio,
                    fecha_final,
                    int(dias_lectivos),
                    int(created_by) if created_by is not None else None,
                    int(notice_id) if notice_id is not None else None,
                ),
            )
            return int(cur.fetchone()["id"])


def list_paa_procedimientos(*, limit: int = 500) -> list[dict]:
    ensure_paa_procedimientos_schema()
    safe_limit = max(1, min(int(limit), 2000))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id,
                    alumno,
                    grupo,
                    fecha_inicio,
                    fecha_final,
                    dias_lectivos,
                    created_at,
                    notice_id
                FROM {TABLE}
                ORDER BY fecha_inicio DESC, id DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            return list(cur.fetchall())


def get_paa_by_id(paa_id: int) -> dict | None:
    ensure_paa_procedimientos_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id, alumno, grupo, fecha_inicio, fecha_final,
                    dias_lectivos, created_at, notice_id
                FROM {TABLE}
                WHERE id = %s
                """,
                (int(paa_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def update_paa_procedimiento(
    *,
    paa_id: int,
    fecha_inicio: date,
    fecha_final: date,
    dias_lectivos: int,
) -> bool:
    ensure_paa_procedimientos_schema()
    if fecha_inicio > fecha_final:
        raise ValueError("La fecha inicial no puede ser posterior a la final")
    if int(dias_lectivos) < 0:
        raise ValueError("Los días lectivos no pueden ser negativos")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET fecha_inicio = %s,
                    fecha_final = %s,
                    dias_lectivos = %s
                WHERE id = %s
                """,
                (fecha_inicio, fecha_final, int(dias_lectivos), int(paa_id)),
            )
            return cur.rowcount > 0


def delete_paa_procedimiento(*, paa_id: int) -> bool:
    """Borra el PAA y, si existe, su aviso publicado."""
    ensure_paa_procedimientos_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT notice_id FROM {TABLE} WHERE id = %s",
                (int(paa_id),),
            )
            row = cur.fetchone()
            if not row:
                return False
            notice_id = row.get("notice_id")
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (int(paa_id),))
            if notice_id is not None:
                cur.execute(
                    "DELETE FROM portal_published_notices WHERE id = %s",
                    (int(notice_id),),
                )
            return True
