"""Expedientes disciplinarios (sanciones)."""

from __future__ import annotations

from datetime import date

from db.connection import get_db

TABLE = "expedientes_disciplinarios"
_schema_ready = False


def ensure_expedientes_disciplinarios_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id                      SERIAL PRIMARY KEY,
                    student_id              INTEGER REFERENCES students(id) ON DELETE SET NULL,
                    alumno                  TEXT NOT NULL,
                    grupo                   TEXT NOT NULL,
                    fecha_inicio_expediente DATE NOT NULL,
                    fecha_final_expediente  DATE,
                    cautelar_inicio         DATE,
                    cautelar_final          DATE,
                    sancion_inicio          DATE,
                    sancion_final           DATE,
                    dias_lectivos           INTEGER NOT NULL DEFAULT 0
                        CHECK (dias_lectivos >= 0),
                    instructor_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    instructor_nombre       TEXT NOT NULL,
                    created_by              INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
                    notice_id               INTEGER
                        REFERENCES portal_published_notices(id) ON DELETE SET NULL,
                    notice_cierre_id        INTEGER
                        REFERENCES portal_published_notices(id) ON DELETE SET NULL,
                    CONSTRAINT exp_fechas_expediente_ok CHECK (
                        fecha_final_expediente IS NULL
                        OR fecha_inicio_expediente <= fecha_final_expediente
                    ),
                    CONSTRAINT exp_fechas_cautelar_ok CHECK (
                        (cautelar_inicio IS NULL AND cautelar_final IS NULL)
                        OR (
                            cautelar_inicio IS NOT NULL
                            AND cautelar_final IS NOT NULL
                            AND cautelar_inicio <= cautelar_final
                        )
                    ),
                    CONSTRAINT exp_fechas_sancion_ok CHECK (
                        (sancion_inicio IS NULL AND sancion_final IS NULL)
                        OR (
                            sancion_inicio IS NOT NULL
                            AND sancion_final IS NOT NULL
                            AND sancion_inicio <= sancion_final
                        )
                    )
                )
                """
            )
            for col in (
                "fecha_final_expediente",
                "cautelar_inicio",
                "cautelar_final",
                "sancion_inicio",
                "sancion_final",
            ):
                cur.execute(
                    f"ALTER TABLE {TABLE} ALTER COLUMN {col} DROP NOT NULL"
                )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS notice_id INTEGER
                    REFERENCES portal_published_notices(id) ON DELETE SET NULL
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS notice_cierre_id INTEGER
                    REFERENCES portal_published_notices(id) ON DELETE SET NULL
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_exp_inicio
                ON {TABLE} (fecha_inicio_expediente DESC)
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_exp_grupo_alumno
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


def create_inicio_expediente(
    *,
    alumno: str,
    grupo: str,
    fecha_inicio_expediente: date,
    cautelar_inicio: date | None,
    cautelar_final: date | None,
    dias_lectivos: int,
    instructor_id: int | None,
    instructor_nombre: str,
    created_by: int | None,
    notice_id: int | None = None,
) -> int:
    ensure_expedientes_disciplinarios_schema()
    alumno_n = (alumno or "").strip()
    grupo_n = (grupo or "").strip()
    instructor_n = (instructor_nombre or "").strip()
    if not alumno_n or not grupo_n:
        raise ValueError("Alumno y grupo son obligatorios")
    if not instructor_n:
        raise ValueError("El instructor es obligatorio")
    if (cautelar_inicio is None) ^ (cautelar_final is None):
        raise ValueError("Indique ambas fechas de la sanción cautelar o ninguna")
    if (
        cautelar_inicio is not None
        and cautelar_final is not None
        and cautelar_inicio > cautelar_final
    ):
        raise ValueError("Fechas de sanción cautelar inválidas")
    if int(dias_lectivos) < 0:
        raise ValueError("Los días lectivos no pueden ser negativos")

    student_id = _student_id_for(grupo=grupo_n, alumno=alumno_n)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    student_id, alumno, grupo,
                    fecha_inicio_expediente,
                    cautelar_inicio, cautelar_final,
                    dias_lectivos, instructor_id, instructor_nombre,
                    created_by, notice_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    student_id,
                    alumno_n,
                    grupo_n,
                    fecha_inicio_expediente,
                    cautelar_inicio,
                    cautelar_final,
                    int(dias_lectivos),
                    int(instructor_id) if instructor_id is not None else None,
                    instructor_n,
                    int(created_by) if created_by is not None else None,
                    int(notice_id) if notice_id is not None else None,
                ),
            )
            return int(cur.fetchone()["id"])


def list_expedientes_disciplinarios(*, limit: int = 500) -> list[dict]:
    return _list_expedientes(limit=limit, abiertos=None)


def list_expedientes_abiertos(*, limit: int = 500) -> list[dict]:
    return _list_expedientes(limit=limit, abiertos=True)


def list_expedientes_cerrados(*, limit: int = 500) -> list[dict]:
    return _list_expedientes(limit=limit, abiertos=False)


def _list_expedientes(*, limit: int = 500, abiertos: bool | None) -> list[dict]:
    ensure_expedientes_disciplinarios_schema()
    safe_limit = max(1, min(int(limit), 2000))
    if abiertos is True:
        where = "WHERE fecha_final_expediente IS NULL"
        order = "fecha_inicio_expediente DESC, id DESC"
    elif abiertos is False:
        where = "WHERE fecha_final_expediente IS NOT NULL"
        order = "fecha_final_expediente DESC, id DESC"
    else:
        where = ""
        order = "fecha_inicio_expediente DESC, id DESC"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id, alumno, grupo,
                    fecha_inicio_expediente, fecha_final_expediente,
                    cautelar_inicio, cautelar_final,
                    sancion_inicio, sancion_final,
                    dias_lectivos, instructor_id, instructor_nombre,
                    created_at, notice_id, notice_cierre_id
                FROM {TABLE}
                {where}
                ORDER BY {order}
                LIMIT %s
                """,
                (safe_limit,),
            )
            return list(cur.fetchall())


def get_expediente_by_id(expediente_id: int) -> dict | None:
    ensure_expedientes_disciplinarios_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id, alumno, grupo,
                    fecha_inicio_expediente, fecha_final_expediente,
                    cautelar_inicio, cautelar_final,
                    sancion_inicio, sancion_final,
                    dias_lectivos, instructor_id, instructor_nombre,
                    created_at, notice_id, notice_cierre_id
                FROM {TABLE}
                WHERE id = %s
                """,
                (int(expediente_id),),
            )
            row = cur.fetchone()
            return dict(row) if row else None


def close_expediente(
    *,
    expediente_id: int,
    fecha_final_expediente: date,
    sancion_inicio: date,
    sancion_final: date,
    dias_lectivos: int,
    notice_cierre_id: int | None = None,
) -> bool:
    ensure_expedientes_disciplinarios_schema()
    if sancion_inicio > sancion_final:
        raise ValueError("Fechas de sanción inválidas")
    if int(dias_lectivos) < 0:
        raise ValueError("Los días lectivos no pueden ser negativos")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET fecha_final_expediente = %s,
                    sancion_inicio = %s,
                    sancion_final = %s,
                    dias_lectivos = %s,
                    notice_cierre_id = COALESCE(%s, notice_cierre_id)
                WHERE id = %s
                  AND fecha_final_expediente IS NULL
                """,
                (
                    fecha_final_expediente,
                    sancion_inicio,
                    sancion_final,
                    int(dias_lectivos),
                    int(notice_cierre_id) if notice_cierre_id is not None else None,
                    int(expediente_id),
                ),
            )
            return cur.rowcount > 0


def compute_expediente_dias_lectivos(
    *,
    cautelar_inicio: date | None,
    cautelar_final: date | None,
    sancion_inicio: date | None,
    sancion_final: date | None,
) -> int:
    """Suma de días lectivos de cautelar + sanción definitiva (rangos inclusive)."""
    from reservas.calendar import count_school_days

    total = 0
    if cautelar_inicio is not None and cautelar_final is not None:
        if cautelar_inicio > cautelar_final:
            raise ValueError("Fechas de sanción cautelar inválidas")
        total += count_school_days(cautelar_inicio, cautelar_final)
    if sancion_inicio is not None and sancion_final is not None:
        if sancion_inicio > sancion_final:
            raise ValueError("Fechas de sanción inválidas")
        total += count_school_days(sancion_inicio, sancion_final)
    return total


def update_expediente(
    *,
    expediente_id: int,
    fecha_inicio_expediente: date,
    fecha_final_expediente: date | None,
    cautelar_inicio: date | None,
    cautelar_final: date | None,
    sancion_inicio: date | None,
    sancion_final: date | None,
    dias_lectivos: int,
    instructor_id: int | None,
    instructor_nombre: str,
) -> bool:
    ensure_expedientes_disciplinarios_schema()
    instructor_n = (instructor_nombre or "").strip()
    if not instructor_n:
        raise ValueError("El instructor es obligatorio")
    if (cautelar_inicio is None) ^ (cautelar_final is None):
        raise ValueError("Indique ambas fechas de la sanción cautelar o ninguna")
    if (sancion_inicio is None) ^ (sancion_final is None):
        raise ValueError("Indique ambas fechas de la sanción o ninguna")
    if (
        fecha_final_expediente is not None
        and fecha_inicio_expediente > fecha_final_expediente
    ):
        raise ValueError("Fechas de expediente inválidas")
    if (
        cautelar_inicio is not None
        and cautelar_final is not None
        and cautelar_inicio > cautelar_final
    ):
        raise ValueError("Fechas de sanción cautelar inválidas")
    if (
        sancion_inicio is not None
        and sancion_final is not None
        and sancion_inicio > sancion_final
    ):
        raise ValueError("Fechas de sanción inválidas")
    if int(dias_lectivos) < 0:
        raise ValueError("Los días lectivos no pueden ser negativos")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET fecha_inicio_expediente = %s,
                    fecha_final_expediente = %s,
                    cautelar_inicio = %s,
                    cautelar_final = %s,
                    sancion_inicio = %s,
                    sancion_final = %s,
                    dias_lectivos = %s,
                    instructor_id = %s,
                    instructor_nombre = %s
                WHERE id = %s
                """,
                (
                    fecha_inicio_expediente,
                    fecha_final_expediente,
                    cautelar_inicio,
                    cautelar_final,
                    sancion_inicio,
                    sancion_final,
                    int(dias_lectivos),
                    int(instructor_id) if instructor_id is not None else None,
                    instructor_n,
                    int(expediente_id),
                ),
            )
            return cur.rowcount > 0


def delete_expediente(*, expediente_id: int) -> bool:
    """Borra el expediente y sus avisos de inicio/cierre si existen."""
    ensure_expedientes_disciplinarios_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT notice_id, notice_cierre_id
                FROM {TABLE}
                WHERE id = %s
                """,
                (int(expediente_id),),
            )
            row = cur.fetchone()
            if not row:
                return False
            notice_ids = [
                int(x)
                for x in (row.get("notice_id"), row.get("notice_cierre_id"))
                if x is not None
            ]
            cur.execute(f"DELETE FROM {TABLE} WHERE id = %s", (int(expediente_id),))
            for nid in notice_ids:
                cur.execute(
                    "DELETE FROM portal_published_notices WHERE id = %s",
                    (nid,),
                )
            return True
