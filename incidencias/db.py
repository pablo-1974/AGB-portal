# db/incidents.py — capa de datos incidencias (monolito campus)
from datetime import datetime, date, timedelta
from db.connection import get_db
from dateutil.relativedelta import relativedelta

from utils.time_madrid import now_madrid, today_madrid

from utils.enums import (
    ESTADO_ABIERTO,
    ESTADO_CERRADO,
    GRAVEDAD_MUY_GRAVE,
    GRAVEDAD_GRAVE,
)
from utils.text import normalize_for_sort


def get_incidents(
    *,
    mode: str,
    user_id: int | None = None,
    tutor_group: str | None = None,
    profesor_id: int | None = None,
    grupo: str | None = None,
    alumno: str | None = None,
    estado: str | None = None,
    gravedad: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
):
    where = []
    params = []

    if mode == "own":
        where.append("teacher_id = %s")
        params.append(user_id)

    if mode == "own_or_tutor":
        visibility_clauses: list[str] = []
        visibility_params: list = []

        if user_id is not None:
            visibility_clauses.append("teacher_id = %s")
            visibility_params.append(user_id)
        if tutor_group:
            visibility_clauses.append("grupo = %s")
            visibility_params.append(tutor_group)

        if not visibility_clauses:
            where.append("1 = 0")
        elif len(visibility_clauses) == 1:
            where.append(visibility_clauses[0])
            params.extend(visibility_params)
        else:
            where.append("(" + " OR ".join(visibility_clauses) + ")")
            params.extend(visibility_params)

    if mode == "all" and profesor_id is not None:
        where.append("teacher_id = %s")
        params.append(profesor_id)

    if grupo:
        where.append("grupo = %s")
        params.append(grupo)

    if alumno:
        where.append("alumno = %s")
        params.append(alumno)

    if estado:
        where.append("estado = %s")
        params.append(estado)

    if gravedad:
        where.append("gravedad_inicial = %s")
        params.append(gravedad)

    if fecha_desde:
        where.append("fecha >= %s")
        params.append(fecha_desde)

    if fecha_hasta:
        where.append("fecha <= %s")
        params.append(fecha_hasta)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    query = f"""
        SELECT
            id,
            fecha,
            hora AS franja,
            grupo,
            alumno,
            descripcion,
            gravedad_inicial,
            gravedad_final,
            estado,
            teacher_name
        FROM incidents
        {where_sql}
        ORDER BY fecha DESC, hora_orden DESC, id DESC
    """

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def create_incident(
    *,
    user_id: int,
    user_name: str,
    grupo: str,
    alumno: str,
    fecha: str,
    hora: str,
    hora_orden: int,
    descripcion: str,
    gravedad: str,
) -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO incidents (
                    teacher_id,
                    teacher_name,
                    grupo,
                    alumno,
                    fecha,
                    hora,
                    hora_orden,
                    descripcion,
                    gravedad_inicial,
                    estado,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    user_id,
                    user_name,
                    grupo,
                    alumno,
                    fecha,
                    hora,
                    hora_orden,
                    descripcion,
                    gravedad,
                    ESTADO_ABIERTO,
                    now_madrid().isoformat(),
                ),
            )
            row = cur.fetchone()
            return int(row["id"])


def close_incident(
    *,
    incident_id: int,
    gravedad_final: str,
    reviewer_id: int,
    reviewer_name: str,
):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE incidents
                SET
                    gravedad_final = %s,
                    estado = %s,
                    reviewed_by = %s,
                    reviewed_by_name = %s,
                    closed_at = %s
                WHERE id = %s
                """,
                (
                    gravedad_final,
                    ESTADO_CERRADO,
                    reviewer_id,
                    reviewer_name,
                    now_madrid().isoformat(),
                    incident_id,
                ),
            )


def has_any_open_incident() -> bool:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM incidents
                WHERE estado = %s
                LIMIT 1
                """,
                (ESTADO_ABIERTO,),
            )
            return cur.fetchone() is not None


def _start_of_current_week_iso() -> str:
    today = today_madrid()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def count_open_incidents() -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM incidents
                WHERE estado = %s
                """,
                (ESTADO_ABIERTO,),
            )
            row = cur.fetchone()
            return next(iter(row.values()))


def count_open_very_serious_incidents() -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM incidents
                WHERE estado = %s
                  AND gravedad_inicial = %s
                """,
                (ESTADO_ABIERTO, GRAVEDAD_MUY_GRAVE),
            )
            row = cur.fetchone()
            return next(iter(row.values()))


def count_incidents_created_this_week() -> int:
    since = _start_of_current_week_iso()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM incidents
                WHERE fecha >= %s
                """,
                (since,),
            )
            row = cur.fetchone()
            return next(iter(row.values()))


def count_incidents_closed_this_week() -> int:
    since = _start_of_current_week_iso()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM incidents
                WHERE estado = %s
                  AND closed_at >= %s
                """,
                (ESTADO_CERRADO, since),
            )
            row = cur.fetchone()
            return next(iter(row.values()))


def count_own_incidents(user_id: int) -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM incidents
                WHERE teacher_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            return next(iter(row.values()))


def get_serious_incident_counts_by_student(
    *,
    fecha_desde: str,
    fecha_hasta: str,
) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COALESCE(NULLIF(BTRIM(g.curso), ''), 'Sin curso') AS curso,
                    UPPER(COALESCE(s.sexo, '')) AS sexo,
                    i.grupo,
                    i.alumno,
                    COUNT(*)::int AS graves_count
                FROM incidents i
                LEFT JOIN students s
                    ON LOWER(BTRIM(s.grupo)) = LOWER(BTRIM(i.grupo))
                   AND LOWER(BTRIM(s.alumno)) = LOWER(BTRIM(i.alumno))
                LEFT JOIN groups g
                    ON LOWER(BTRIM(g.name)) = LOWER(BTRIM(i.grupo))
                WHERE i.fecha >= %s
                  AND i.fecha <= %s
                  AND COALESCE(i.gravedad_final, i.gravedad_inicial) IN (%s, %s)
                  AND i.alumno IS NOT NULL
                  AND BTRIM(i.alumno) <> ''
                GROUP BY
                    COALESCE(NULLIF(BTRIM(g.curso), ''), 'Sin curso'),
                    UPPER(COALESCE(s.sexo, '')),
                    i.grupo,
                    i.alumno
                ORDER BY curso, i.grupo, i.alumno
                """,
                (fecha_desde, fecha_hasta, GRAVEDAD_GRAVE, GRAVEDAD_MUY_GRAVE),
            )
            rows = list(cur.fetchall())
    rows.sort(
        key=lambda r: (
            str(r.get("curso") or ""),
            str(r.get("grupo") or ""),
            normalize_for_sort(str(r.get("alumno") or "")),
        )
    )
    return rows


def get_students_ranking(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
):
    where = []
    params = []

    if fecha_desde:
        where.append("fecha >= %s")
        params.append(fecha_desde)

    if fecha_hasta:
        where.append("fecha <= %s")
        params.append(fecha_hasta)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                WITH alumno_grupo_counts AS (
                    SELECT
                        alumno,
                        grupo,
                        COUNT(*) AS cnt
                    FROM incidents
                    {where_sql}
                    GROUP BY alumno, grupo
                ),
                alumno_totals AS (
                    SELECT
                        alumno,
                        SUM(cnt) AS total_cnt
                    FROM alumno_grupo_counts
                    GROUP BY alumno
                ),
                alumno_main_group AS (
                    SELECT DISTINCT ON (alumno)
                        alumno,
                        grupo
                    FROM alumno_grupo_counts
                    ORDER BY alumno, cnt DESC, grupo
                )
                SELECT
                    ROW_NUMBER() OVER (ORDER BY at.total_cnt DESC, at.alumno) AS posicion,
                    at.alumno,
                    amg.grupo,
                    at.total_cnt AS num_incidencias
                FROM alumno_totals at
                JOIN alumno_main_group amg
                  ON amg.alumno = at.alumno
                ORDER BY at.total_cnt DESC, at.alumno
                """,
                params,
            )
            rows = [dict(r) for r in cur.fetchall()]
    rows.sort(
        key=lambda r: (-int(r["num_incidencias"]), normalize_for_sort(str(r.get("alumno") or "")))
    )
    for i, r in enumerate(rows, start=1):
        r["posicion"] = i
    return rows


def get_groups_ranking(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
):
    where = []
    params = []

    if fecha_desde:
        where.append("fecha >= %s")
        params.append(fecha_desde)

    if fecha_hasta:
        where.append("fecha <= %s")
        params.append(fecha_hasta)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, grupo) AS posicion,
                    grupo,
                    COUNT(*) AS num_incidencias
                FROM incidents
                {where_sql}
                GROUP BY grupo
                ORDER BY num_incidencias DESC, grupo
                """,
                params,
            )
            rows = [dict(r) for r in cur.fetchall()]
    rows.sort(
        key=lambda r: (-int(r["num_incidencias"]), normalize_for_sort(str(r.get("grupo") or "")))
    )
    for i, r in enumerate(rows, start=1):
        r["posicion"] = i
    return rows


def get_teachers_ranking(
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
):
    where = []
    params = []

    if fecha_desde:
        where.append("fecha >= %s")
        params.append(fecha_desde)

    if fecha_hasta:
        where.append("fecha <= %s")
        params.append(fecha_hasta)

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, teacher_name) AS posicion,
                    teacher_name AS profesor,
                    COUNT(*) AS num_incidencias
                FROM incidents
                {where_sql}
                GROUP BY teacher_name
                ORDER BY num_incidencias DESC, profesor
                """,
                params,
            )
            rows = [dict(r) for r in cur.fetchall()]
    rows.sort(
        key=lambda r: (-int(r["num_incidencias"]), normalize_for_sort(str(r.get("profesor") or "")))
    )
    for i, r in enumerate(rows, start=1):
        r["posicion"] = i
    return rows


def get_excursion_eligibility(
    *,
    fecha_excursion: str,
    grupos: list[str],
):
    fecha_exc = datetime.fromisoformat(fecha_excursion).date()
    fecha_desde = fecha_exc - relativedelta(months=1)
    fecha_hasta = fecha_exc - relativedelta(days=1)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    alumno,
                    grupo,
                    COUNT(*) AS total_faltas,
                    SUM(
                        CASE
                            WHEN gravedad_final IN ('grave', 'muy grave')
                            THEN 1 ELSE 0
                        END
                    ) AS faltas_graves
                FROM incidents
                WHERE estado = %s
                  AND fecha BETWEEN %s AND %s
                  AND grupo = ANY(%s)
                  AND alumno IS NOT NULL
                GROUP BY alumno, grupo
                ORDER BY grupo, alumno
                """,
                (
                    ESTADO_CERRADO,
                    fecha_desde.isoformat(),
                    fecha_hasta.isoformat(),
                    grupos,
                ),
            )

            rows = cur.fetchall()

    sancionados = []
    posibles_amnistiados = []

    for r in rows:
        alumno = r["alumno"]
        grupo = r["grupo"]
        total = r["total_faltas"]
        graves = r["faltas_graves"]

        if graves >= 1 or total >= 2:
            sancionados.append({
                "grupo": grupo,
                "alumno": alumno,
                "total": total,
                "graves": graves or 0,
            })
        elif total == 1 and graves == 0:
            posibles_amnistiados.append({
                "grupo": grupo,
                "alumno": alumno,
                "total": total,
                "graves": 0,
            })

    def _sort_grupo_alumno(item: dict) -> tuple[str, str]:
        return (
            str(item.get("grupo") or ""),
            normalize_for_sort(str(item.get("alumno") or "")),
        )

    sancionados.sort(key=_sort_grupo_alumno)
    posibles_amnistiados.sort(key=_sort_grupo_alumno)
    return sancionados, posibles_amnistiados


def get_open_incidents_for_closing():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    fecha,
                    hora AS franja,
                    grupo,
                    alumno,
                    descripcion,
                    gravedad_inicial,
                    teacher_name
                FROM incidents
                WHERE estado = %s
                ORDER BY
                    CASE gravedad_inicial
                        WHEN %s THEN 1
                        WHEN %s THEN 2
                        ELSE 3
                    END,
                    fecha ASC,
                    hora_orden ASC,
                    id ASC
                """,
                (
                    ESTADO_ABIERTO,
                    GRAVEDAD_MUY_GRAVE,
                    GRAVEDAD_GRAVE,
                ),
            )
            return cur.fetchall()


def count_total_incidents() -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM incidents
                """
            )
            row = cur.fetchone()
            return next(iter(row.values()))


def count_incidents(
    *,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    estado: str | None = None,
) -> int:
    """Recuento con los mismos filtros de fecha/estado que ``get_incidents``."""
    where: list[str] = []
    params: list = []
    if fecha_desde:
        where.append("fecha >= %s")
        params.append(fecha_desde)
    if fecha_hasta:
        where.append("fecha <= %s")
        params.append(fecha_hasta)
    if estado:
        where.append("estado = %s")
        params.append(estado)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM incidents
                {where_sql}
                """,
                params,
            )
            row = cur.fetchone()
            return next(iter(row.values()))


def count_students_with_incidents() -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT alumno)
                FROM incidents
                WHERE alumno IS NOT NULL
                  AND alumno != ''
                """
            )
            row = cur.fetchone()
            return next(iter(row.values()))


def count_groups_with_incidents() -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT grupo)
                FROM incidents
                WHERE grupo IS NOT NULL
                  AND grupo != ''
                """
            )
            row = cur.fetchone()
            return next(iter(row.values()))


def get_incident_by_id(incident_id: int):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    fecha,
                    hora,
                    grupo,
                    alumno,
                    descripcion,
                    gravedad_inicial,
                    gravedad_final,
                    estado,
                    teacher_id,
                    teacher_name,
                    created_at
                FROM incidents
                WHERE id = %s
                """,
                (incident_id,),
            )
            return cur.fetchone()


def update_incident(
    *,
    incident_id: int,
    grupo: str,
    alumno: str,
    descripcion: str,
    gravedad_inicial: str,
    estado: str,
):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE incidents
                SET
                    grupo = %s,
                    alumno = %s,
                    descripcion = %s,
                    gravedad_inicial = %s,
                    estado = %s
                WHERE id = %s
                """,
                (
                    grupo,
                    alumno,
                    descripcion,
                    gravedad_inicial,
                    estado,
                    incident_id,
                ),
            )


def delete_incident(incident_id: int):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM incidents
                WHERE id = %s
                """,
                (incident_id,),
            )
