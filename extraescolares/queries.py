"""Consultas de actividades extraescolares."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from db.connection import get_db
from utils.time_madrid import today_madrid
from db.extraescolares_schema import ensure_extraescolares_schema
from extraescolares.calendar_view import format_date_es
from utils.school_hours import mask_to_human
from utils.text import normalize_for_sort


def _as_date(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val).strip()[:10])
    except ValueError:
        return None


def _parse_confirmed_at(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return None


def _parse_cancelled_at(val) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return None


def confirmation_deadline(fecha: date | None) -> date | None:
    if not fecha:
        return None
    return fecha - timedelta(days=1)


def activity_is_editable(
    *,
    fecha: date | None,
    confirmed_at: datetime | None,
    cancelled_at: datetime | None,
    today: date,
) -> bool:
    if cancelled_at or not fecha or fecha < today:
        return False
    return confirmed_at is None


def activity_is_staff_editable(
    *,
    fecha: date | None,
    confirmed_at: datetime | None,
    cancelled_at: datetime | None,
    today: date,
) -> bool:
    """Confirmada por el organizador y aún no realizada (fecha futura o hoy)."""
    if cancelled_at or not fecha or fecha < today:
        return False
    return confirmed_at is not None


def can_cancel_activity(
    *,
    fecha: date | None,
    cancelled_at: datetime | None,
    today: date,
) -> bool:
    """El organizador puede anular solo antes del día de la actividad."""
    if cancelled_at or not fecha:
        return False
    return fecha > today


def can_confirm_activity(
    *,
    fecha: date | None,
    confirmed_at: datetime | None,
    cancelled_at: datetime | None,
    today: date,
) -> bool:
    """La confirmación del organizador debe hacerse como tarde el día anterior."""
    if cancelled_at:
        return False
    if not fecha or confirmed_at is not None:
        return False
    if fecha <= today:
        return False
    return True


def _activity_status_label(
    *,
    is_past: bool,
    cancelled_at: datetime | None,
    confirmed_at: datetime | None,
) -> str:
    if cancelled_at:
        return "Anulada"
    if is_past:
        return "Realizada"
    if confirmed_at:
        return "Confirmada"
    return "Pendiente de confirmación"


def _activity_summary_from_row(row: dict) -> dict:
    fd = _as_date(row["fecha"])
    confirmed_at = _parse_confirmed_at(row.get("confirmed_at"))
    cancelled_at = _parse_cancelled_at(row.get("cancelled_at"))
    today = today_madrid()
    editable = activity_is_editable(
        fecha=fd,
        confirmed_at=confirmed_at,
        cancelled_at=cancelled_at,
        today=today,
    )
    is_past = bool(fd and fd < today)
    deadline = confirmation_deadline(fd)
    can_confirm = can_confirm_activity(
        fecha=fd,
        confirmed_at=confirmed_at,
        cancelled_at=cancelled_at,
        today=today,
    )
    staff_editable = activity_is_staff_editable(
        fecha=fd,
        confirmed_at=confirmed_at,
        cancelled_at=cancelled_at,
        today=today,
    )
    can_cancel = can_cancel_activity(
        fecha=fd,
        cancelled_at=cancelled_at,
        today=today,
    )
    return {
        "id": int(row["id"]),
        "fecha": fd,
        "fecha_iso": fd.isoformat() if fd else "",
        "actividad": (row.get("actividad") or "").strip(),
        "lugar": (row.get("lugar") or "").strip() or None,
        "departamento": (row.get("departamento") or "").strip() or None,
        "responsable_id": int(row["responsable_id"]),
        "responsable_name": (row.get("responsable_name") or "").strip(),
        "hours_mask": int(row.get("hours_mask") or 0),
        "hours_display": mask_to_human(int(row.get("hours_mask") or 0)),
        "acompanantes_names": (row.get("acompanantes_names") or "").strip() or None,
        "total_alumnos": int(row.get("total_alumnos") or 0),
        "confirmados": int(row.get("confirmados") or 0),
        "confirmed_at": confirmed_at,
        "cancelled_at": cancelled_at,
        "is_cancelled": cancelled_at is not None,
        "is_past": is_past,
        "is_editable": editable,
        "is_staff_editable": staff_editable,
        "can_confirm": can_confirm,
        "can_cancel": can_cancel,
        "confirmation_deadline": deadline,
        "confirmation_deadline_iso": deadline.isoformat() if deadline else "",
        "status_label": _activity_status_label(
            is_past=is_past,
            cancelled_at=cancelled_at,
            confirmed_at=confirmed_at,
        ),
    }


def list_extraescolares_between(
    date_from: date,
    date_to: date,
    *,
    include_cancelled: bool = True,
) -> list[dict]:
    """Actividades en un rango de fechas, con recuento de alumnado."""
    ensure_extraescolares_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    e.id,
                    e.fecha,
                    e.actividad,
                    e.lugar,
                    e.departamento,
                    e.responsable_id,
                    e.hours_mask,
                    e.confirmed_at,
                    e.cancelled_at,
                    u.name AS responsable_name,
                    COUNT(DISTINCT a.id)::int AS total_alumnos,
                    COUNT(DISTINCT a.id) FILTER (WHERE a.estado = 'confirmado')::int AS confirmados,
                    COALESCE(
                        string_agg(DISTINCT ua.name, ', ' ORDER BY ua.name)
                        FILTER (WHERE ua.id IS NOT NULL),
                        ''
                    ) AS acompanantes_names
                FROM extraescolares e
                JOIN users u ON u.id = e.responsable_id
                LEFT JOIN extraescolar_alumnos a ON a.extraescolar_id = e.id
                LEFT JOIN extraescolar_acompanantes ac ON ac.extraescolar_id = e.id
                LEFT JOIN users ua ON ua.id = ac.user_id
                WHERE e.fecha >= %s AND e.fecha <= %s
                  AND (%s OR e.cancelled_at IS NULL)
                GROUP BY e.id, e.fecha, e.actividad, e.lugar, e.departamento,
                         e.responsable_id, e.hours_mask, e.confirmed_at, e.cancelled_at, u.name
                ORDER BY e.fecha ASC, e.actividad ASC
                """,
                (date_from, date_to, include_cancelled),
            )
            rows = cur.fetchall()

    out: list[dict] = []
    for row in rows:
        out.append(_activity_summary_from_row(row))
    return out


def activities_by_date(activities: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for act in activities:
        iso = act.get("fecha_iso") or ""
        if not iso:
            continue
        grouped.setdefault(iso, []).append(act)
    return grouped


def attach_calendar_student_details(activities: list[dict]) -> list[dict]:
    """Añade grupos implicados y listado de alumnos para el panel del calendario."""
    if not activities:
        return activities

    ids = [int(a["id"]) for a in activities]
    by_act: dict[int, list[dict]] = {i: [] for i in ids}

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT extraescolar_id, grupo, alumno, estado
                FROM extraescolar_alumnos
                WHERE extraescolar_id = ANY(%s)
                ORDER BY extraescolar_id ASC, grupo ASC, alumno ASC
                """,
                (ids,),
            )
            for r in cur.fetchall():
                aid = int(r["extraescolar_id"])
                by_act.setdefault(aid, []).append(
                    {
                        "grupo": str(r.get("grupo") or "").strip(),
                        "alumno": str(r.get("alumno") or "").strip(),
                        "estado": str(r.get("estado") or "no_confirmado"),
                    }
                )

    for act in activities:
        students = by_act.get(int(act["id"]), [])
        students.sort(
            key=lambda s: (
                normalize_for_sort(s.get("grupo") or ""),
                normalize_for_sort(s.get("alumno") or ""),
            )
        )
        grupos = sorted(
            {s["grupo"] for s in students if s.get("grupo")},
            key=normalize_for_sort,
        )
        act["students"] = students
        act["grupos"] = grupos
        act["grupos_label"] = ", ".join(grupos) if grupos else None

    return activities


def list_departamentos_didacticos() -> list[str]:
    """Departamentos distintos definidos en el profesorado (users.departamento)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT TRIM(u.departamento) AS d
                FROM users u
                WHERE u.departamento IS NOT NULL
                  AND TRIM(u.departamento) <> ''
                """
            )
            rows = cur.fetchall()
    names = sorted(
        {str(r["d"]).strip() for r in rows if r.get("d")},
        key=normalize_for_sort,
    )
    return names


def list_students_for_groups(grupos: list[str]) -> list[dict]:
    """Alumnado de los grupos indicados, ordenado por grupo y nombre."""
    clean = sorted({g.strip() for g in grupos if g and str(g).strip()}, key=normalize_for_sort)
    if not clean:
        return []

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, grupo, alumno
                FROM students
                WHERE TRIM(COALESCE(grupo, '')) = ANY(%s)
                  AND TRIM(COALESCE(alumno, '')) <> ''
                """,
                (clean,),
            )
            rows = list(cur.fetchall())

    rows.sort(
        key=lambda r: (
            normalize_for_sort(str(r.get("grupo") or "")),
            normalize_for_sort(str(r.get("alumno") or "")),
        )
    )
    return [
        {
            "id": int(r["id"]),
            "grupo": str(r["grupo"]).strip(),
            "alumno": str(r["alumno"]).strip(),
        }
        for r in rows
    ]


def create_extraescolar_activity(
    *,
    fecha: date,
    actividad: str,
    lugar: str | None,
    departamento: str,
    responsable_id: int,
    hours_mask: int,
    acompanante_ids: list[int],
    student_ids: list[int],
) -> int:
    """Crea actividad e inscribe alumnado seleccionado (estado no_confirmado)."""
    actividad = (actividad or "").strip()
    departamento = (departamento or "").strip()
    lugar = (lugar or "").strip() or None

    if not actividad:
        raise ValueError("El nombre de la actividad es obligatorio")
    if not departamento:
        raise ValueError("El departamento didáctico es obligatorio")
    if not student_ids:
        raise ValueError("Debe seleccionar al menos un alumno")

    unique_ids = sorted({int(i) for i in student_ids if int(i) > 0})
    if not unique_ids:
        raise ValueError("Debe seleccionar al menos un alumno")

    rid = int(responsable_id)
    companion_ids = sorted(
        {int(i) for i in acompanante_ids if int(i) > 0 and int(i) != rid}
    )

    ensure_extraescolares_schema()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, grupo, alumno
                FROM students
                WHERE id = ANY(%s)
                """,
                (unique_ids,),
            )
            student_rows = {int(r["id"]): r for r in cur.fetchall()}
            missing = [i for i in unique_ids if i not in student_rows]
            if missing:
                raise ValueError("Hay alumnos seleccionados que ya no existen en el maestro de datos")

            cur.execute(
                """
                INSERT INTO extraescolares (
                    fecha, actividad, lugar, departamento, responsable_id, hours_mask
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (fecha, actividad, lugar, departamento, rid, int(hours_mask)),
            )
            act_id = int(cur.fetchone()["id"])

            if companion_ids:
                cur.execute(
                    """
                    SELECT id FROM users
                    WHERE id = ANY(%s) AND active = 1
                    """,
                    (companion_ids,),
                )
                valid_companions = {int(r["id"]) for r in cur.fetchall()}
                missing_comp = [i for i in companion_ids if i not in valid_companions]
                if missing_comp:
                    raise ValueError("Hay profesores acompañantes que no existen o no están activos")
                for uid in companion_ids:
                    cur.execute(
                        """
                        INSERT INTO extraescolar_acompanantes (extraescolar_id, user_id)
                        VALUES (%s, %s)
                        """,
                        (act_id, uid),
                    )

            for sid in unique_ids:
                row = student_rows[sid]
                cur.execute(
                    """
                    INSERT INTO extraescolar_alumnos (
                        extraescolar_id, student_id, alumno, grupo, estado
                    )
                    VALUES (%s, %s, %s, %s, 'no_confirmado')
                    """,
                    (
                        act_id,
                        sid,
                        str(row["alumno"]).strip(),
                        str(row["grupo"]).strip(),
                    ),
                )
            return act_id


def list_extraescolares_by_responsable(
    responsable_id: int,
    date_from: date,
    date_to: date,
) -> list[dict]:
    """Actividades del organizador en el curso."""
    ensure_extraescolares_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    e.id,
                    e.fecha,
                    e.actividad,
                    e.lugar,
                    e.departamento,
                    e.responsable_id,
                    e.hours_mask,
                    e.confirmed_at,
                    e.cancelled_at,
                    u.name AS responsable_name,
                    COUNT(DISTINCT a.id)::int AS total_alumnos,
                    COUNT(DISTINCT a.id) FILTER (WHERE a.estado = 'confirmado')::int AS confirmados,
                    COALESCE(
                        string_agg(DISTINCT ua.name, ', ' ORDER BY ua.name)
                        FILTER (WHERE ua.id IS NOT NULL),
                        ''
                    ) AS acompanantes_names
                FROM extraescolares e
                JOIN users u ON u.id = e.responsable_id
                LEFT JOIN extraescolar_alumnos a ON a.extraescolar_id = e.id
                LEFT JOIN extraescolar_acompanantes ac ON ac.extraescolar_id = e.id
                LEFT JOIN users ua ON ua.id = ac.user_id
                WHERE e.responsable_id = %s
                  AND e.fecha >= %s AND e.fecha <= %s
                GROUP BY e.id, e.fecha, e.actividad, e.lugar, e.departamento,
                         e.responsable_id, e.hours_mask, e.confirmed_at, e.cancelled_at, u.name
                ORDER BY e.fecha ASC, e.actividad ASC
                """,
                (int(responsable_id), date_from, date_to),
            )
            rows = cur.fetchall()
    return [_activity_summary_from_row(r) for r in rows]


def get_extraescolar_by_id(activity_id: int) -> dict | None:
    ensure_extraescolares_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    e.id,
                    e.fecha,
                    e.actividad,
                    e.lugar,
                    e.departamento,
                    e.responsable_id,
                    e.hours_mask,
                    e.confirmed_at,
                    e.cancelled_at,
                    u.name AS responsable_name,
                    COUNT(DISTINCT a.id)::int AS total_alumnos,
                    COUNT(DISTINCT a.id) FILTER (WHERE a.estado = 'confirmado')::int AS confirmados,
                    COALESCE(
                        string_agg(DISTINCT ua.name, ', ' ORDER BY ua.name)
                        FILTER (WHERE ua.id IS NOT NULL),
                        ''
                    ) AS acompanantes_names
                FROM extraescolares e
                JOIN users u ON u.id = e.responsable_id
                LEFT JOIN extraescolar_alumnos a ON a.extraescolar_id = e.id
                LEFT JOIN extraescolar_acompanantes ac ON ac.extraescolar_id = e.id
                LEFT JOIN users ua ON ua.id = ac.user_id
                WHERE e.id = %s
                GROUP BY e.id, e.fecha, e.actividad, e.lugar, e.departamento,
                         e.responsable_id, e.hours_mask, e.confirmed_at, e.cancelled_at, u.name
                """,
                (int(activity_id),),
            )
            row = cur.fetchone()
    if not row:
        return None
    act = _activity_summary_from_row(row)
    act["students"] = list_activity_students(int(activity_id))
    act["acompanante_ids"] = list_activity_acompanante_ids(int(activity_id))
    return act


def get_extraescolar_for_responsable(activity_id: int, responsable_id: int) -> dict | None:
    act = get_extraescolar_by_id(activity_id)
    if not act or int(act["responsable_id"]) != int(responsable_id):
        return None
    return act


def list_activity_students(activity_id: int) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, student_id, alumno, grupo, estado
                FROM extraescolar_alumnos
                WHERE extraescolar_id = %s
                """,
                (int(activity_id),),
            )
            rows = list(cur.fetchall())
    out: list[dict] = []
    for r in rows:
        sid = r.get("student_id")
        out.append(
            {
                "enrollment_id": int(r["id"]),
                "id": int(sid) if sid is not None else None,
                "student_id": int(sid) if sid is not None else None,
                "alumno": str(r.get("alumno") or "").strip(),
                "grupo": str(r.get("grupo") or "").strip(),
                "estado": str(r.get("estado") or "no_confirmado"),
            }
        )
    out.sort(
        key=lambda s: (
            normalize_for_sort(s.get("grupo") or ""),
            normalize_for_sort(s.get("alumno") or ""),
        )
    )
    return out


def list_activity_acompanante_ids(activity_id: int) -> list[int]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id
                FROM extraescolar_acompanantes
                WHERE extraescolar_id = %s
                ORDER BY user_id ASC
                """,
                (int(activity_id),),
            )
            rows = cur.fetchall()
    return [int(r["user_id"]) for r in rows]


def update_extraescolar_activity(
    *,
    activity_id: int,
    editor_id: int,
    fecha: date,
    student_ids: list[int],
    acompanante_ids: list[int],
    as_staff: bool = False,
) -> None:
    act = get_extraescolar_by_id(activity_id)
    if not act:
        raise ValueError("Actividad no encontrada")
    if act.get("is_cancelled"):
        raise ValueError("Esta actividad está anulada")

    if as_staff:
        if not act.get("is_staff_editable"):
            raise ValueError("Esta actividad confirmada ya no admite edición")
    else:
        if int(act["responsable_id"]) != int(editor_id) or not act["is_editable"]:
            raise ValueError("Esta actividad ya no se puede editar")

    if fecha < today_madrid():
        raise ValueError("La fecha debe ser hoy o un día futuro")

    unique_ids = sorted({int(i) for i in student_ids if int(i) > 0})
    if not unique_ids:
        raise ValueError("Debe mantener al menos un alumno inscrito")

    rid = int(act["responsable_id"])
    companion_ids = sorted(
        {int(i) for i in acompanante_ids if int(i) > 0 and int(i) != rid}
    )

    ensure_extraescolares_schema()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, grupo, alumno
                FROM students
                WHERE id = ANY(%s)
                """,
                (unique_ids,),
            )
            student_rows = {int(r["id"]): r for r in cur.fetchall()}
            missing = [i for i in unique_ids if i not in student_rows]
            if missing:
                raise ValueError("Hay alumnos seleccionados que ya no existen en el maestro de datos")

            if as_staff:
                cur.execute(
                    """
                    UPDATE extraescolares
                    SET fecha = %s, updated_at = now()
                    WHERE id = %s
                      AND confirmed_at IS NOT NULL
                      AND fecha >= %s
                    """,
                    (fecha, int(activity_id), today_madrid()),
                )
            else:
                cur.execute(
                    """
                    UPDATE extraescolares
                    SET fecha = %s, updated_at = now()
                    WHERE id = %s AND responsable_id = %s AND confirmed_at IS NULL
                    """,
                    (fecha, int(activity_id), rid),
                )
            if cur.rowcount != 1:
                raise ValueError("No se pudo actualizar la actividad")

            cur.execute(
                """
                SELECT id, student_id, estado
                FROM extraescolar_alumnos
                WHERE extraescolar_id = %s
                """,
                (int(activity_id),),
            )
            existing = {
                int(r["student_id"]): r
                for r in cur.fetchall()
                if r.get("student_id") is not None
            }
            keep = set(unique_ids)
            for sid, row in existing.items():
                if sid not in keep:
                    cur.execute(
                        "DELETE FROM extraescolar_alumnos WHERE id = %s",
                        (int(row["id"]),),
                    )
            for sid in unique_ids:
                if sid in existing:
                    continue
                row = student_rows[sid]
                cur.execute(
                    """
                    INSERT INTO extraescolar_alumnos (
                        extraescolar_id, student_id, alumno, grupo, estado
                    )
                    VALUES (%s, %s, %s, %s, 'no_confirmado')
                    """,
                    (
                        int(activity_id),
                        sid,
                        str(row["alumno"]).strip(),
                        str(row["grupo"]).strip(),
                    ),
                )

            cur.execute(
                "DELETE FROM extraescolar_acompanantes WHERE extraescolar_id = %s",
                (int(activity_id),),
            )
            if companion_ids:
                cur.execute(
                    """
                    SELECT id FROM users
                    WHERE id = ANY(%s) AND active = 1
                    """,
                    (companion_ids,),
                )
                valid_companions = {int(r["id"]) for r in cur.fetchall()}
                missing_comp = [i for i in companion_ids if i not in valid_companions]
                if missing_comp:
                    raise ValueError("Hay profesores acompañantes que no existen o no están activos")
                for uid in companion_ids:
                    cur.execute(
                        """
                        INSERT INTO extraescolar_acompanantes (extraescolar_id, user_id)
                        VALUES (%s, %s)
                        """,
                        (int(activity_id), uid),
                    )


def confirm_extraescolar_by_organizer(*, activity_id: int, responsable_id: int) -> None:
    act = get_extraescolar_for_responsable(activity_id, responsable_id)
    if not act:
        raise ValueError("Actividad no encontrada")
    if act.get("is_cancelled"):
        raise ValueError("No se puede confirmar una actividad anulada")
    if act["is_past"]:
        raise ValueError("No se puede confirmar una actividad ya realizada")
    if act.get("confirmed_at"):
        raise ValueError("La actividad ya estaba confirmada")
    fd = act.get("fecha")
    if not fd or fd <= today_madrid():
        raise ValueError(
            "La confirmación debe realizarse como tarde el día anterior a la actividad"
        )

    ensure_extraescolares_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE extraescolares
                SET confirmed_at = now(), updated_at = now()
                WHERE id = %s AND responsable_id = %s
                  AND confirmed_at IS NULL AND cancelled_at IS NULL
                """,
                (int(activity_id), int(responsable_id)),
            )
            if cur.rowcount != 1:
                raise ValueError("No se pudo confirmar la actividad")
            cur.execute(
                """
                UPDATE extraescolar_alumnos
                SET estado = 'confirmado', updated_at = now()
                WHERE extraescolar_id = %s
                """,
                (int(activity_id),),
            )


def cancel_extraescolar_by_organizer(*, activity_id: int, responsable_id: int) -> None:
    act = get_extraescolar_for_responsable(activity_id, responsable_id)
    if not act:
        raise ValueError("Actividad no encontrada")
    if not act.get("can_cancel"):
        raise ValueError(
            "Solo puede anular actividades futuras que aún no estén anuladas"
        )

    ensure_extraescolares_schema()
    today = today_madrid()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE extraescolares
                SET cancelled_at = now(), updated_at = now()
                WHERE id = %s AND responsable_id = %s
                  AND cancelled_at IS NULL AND fecha > %s
                """,
                (int(activity_id), int(responsable_id), today),
            )
            if cur.rowcount != 1:
                raise ValueError("No se pudo anular la actividad")


def delete_extraescolar_by_admin(*, activity_id: int) -> None:
    act = get_extraescolar_by_id(activity_id)
    if not act:
        raise ValueError("Actividad no encontrada")

    ensure_extraescolares_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM extraescolares WHERE id = %s",
                (int(activity_id),),
            )
            if cur.rowcount != 1:
                raise ValueError("No se pudo eliminar la actividad")


def list_unconfirmed_activities_for_portal_aviso(
    responsable_id: int,
    *,
    today: date | None = None,
    days_ahead: int = 15,
) -> list[dict]:
    """Actividades sin confirmar del organizador, a ≤15 días de la fecha (avisos del portal)."""
    today = today or today_madrid()
    horizon = today + timedelta(days=int(days_ahead))
    ensure_extraescolares_schema()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, fecha, actividad
                FROM extraescolares
                WHERE responsable_id = %s
                  AND confirmed_at IS NULL
                  AND cancelled_at IS NULL
                  AND fecha >= %s
                  AND fecha <= %s
                ORDER BY fecha ASC, actividad ASC
                """,
                (int(responsable_id), today, horizon),
            )
            rows = cur.fetchall()

    out: list[dict] = []
    for row in rows:
        fd = _as_date(row["fecha"])
        out.append(
            {
                "id": int(row["id"]),
                "fecha": fd,
                "fecha_iso": fd.isoformat() if fd else "",
                "fecha_display": format_date_es(fd) if fd else "",
                "actividad": (row.get("actividad") or "").strip(),
            }
        )
    return out
