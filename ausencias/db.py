from __future__ import annotations

from datetime import date

from db.connection import get_db
from utils.text import normalize_for_sort


def _date_ord(d: date | None) -> int:
    return 0 if d is None else d.toordinal()


def ensure_ausencias_schema() -> None:
    """Crea (o ajusta) tablas de ausencias en la BD compartida."""
    with get_db() as conn:
        with conn.cursor() as cur:
            # users fusionada
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS alias TEXT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS titular BOOLEAN")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS active SMALLINT")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_by INTEGER")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS departamento TEXT")

            cur.execute("UPDATE users SET status = 'activo' WHERE status IS NULL")
            cur.execute("UPDATE users SET titular = TRUE WHERE titular IS NULL")
            cur.execute("UPDATE users SET active = 1 WHERE active IS NULL")
            cur.execute("UPDATE users SET created_at = now() WHERE created_at IS NULL")
            cur.execute("UPDATE users SET must_change_password = FALSE WHERE must_change_password IS NULL")

            cur.execute("ALTER TABLE users ALTER COLUMN status SET DEFAULT 'activo'")
            cur.execute("ALTER TABLE users ALTER COLUMN titular SET DEFAULT TRUE")
            cur.execute("ALTER TABLE users ALTER COLUMN active SET DEFAULT 1")
            cur.execute("ALTER TABLE users ALTER COLUMN created_at SET DEFAULT now()")
            cur.execute("ALTER TABLE users ALTER COLUMN must_change_password SET DEFAULT FALSE")

            cur.execute("ALTER TABLE users ALTER COLUMN status SET NOT NULL")
            cur.execute("ALTER TABLE users ALTER COLUMN titular SET NOT NULL")
            cur.execute("ALTER TABLE users ALTER COLUMN active SET NOT NULL")
            cur.execute("ALTER TABLE users ALTER COLUMN created_at SET NOT NULL")
            cur.execute("ALTER TABLE users ALTER COLUMN must_change_password SET NOT NULL")
            cur.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")

            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'users_created_by_fkey'
                    ) THEN
                        ALTER TABLE users
                        ADD CONSTRAINT users_created_by_fkey
                        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;
                    END IF;
                END $$;
                """
            )
            cur.execute(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint WHERE conname = 'users_active_check'
                    ) THEN
                        ALTER TABLE users
                        ADD CONSTRAINT users_active_check CHECK (active IN (0, 1));
                    END IF;
                END $$;
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_alias ON users (alias)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_users_role ON users (role)")

            # schedule_slots
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule_slots (
                    id SERIAL PRIMARY KEY,
                    teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    day_index INTEGER NOT NULL CHECK (day_index BETWEEN 0 AND 4),
                    hour_index INTEGER NOT NULL CHECK (hour_index BETWEEN 0 AND 6),
                    type TEXT NOT NULL CHECK (type IN ('CLASS', 'GUARD')),
                    guard_type TEXT,
                    "group" TEXT,
                    room TEXT,
                    subject TEXT,
                    source TEXT DEFAULT 'import'
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_schedule_slots_teacher_id ON schedule_slots (teacher_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_schedule_slots_day_hour ON schedule_slots (day_index, hour_index)"
            )

            # leaves
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS leaves (
                    id SERIAL PRIMARY KEY,
                    teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    parent_leave_id INTEGER REFERENCES leaves(id) ON DELETE CASCADE,
                    start_date DATE NOT NULL,
                    end_date DATE,
                    cause TEXT NOT NULL DEFAULT '',
                    substitute_teacher_id INTEGER REFERENCES users(id),
                    substitute_start_date DATE,
                    substitute_end_date DATE,
                    category TEXT,
                    is_substitution BOOLEAN NOT NULL DEFAULT FALSE,
                    leave_kind TEXT NOT NULL DEFAULT 'baja'
                )
                """
            )
            cur.execute(
                "ALTER TABLE leaves ADD COLUMN IF NOT EXISTS leave_kind TEXT NOT NULL DEFAULT 'baja'"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_leaves_teacher_id ON leaves (teacher_id)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_leaves_parent_leave_id ON leaves (parent_leave_id)"
            )
            cur.execute(
                """
                UPDATE users u
                SET titular = FALSE
                WHERE EXISTS (
                    SELECT 1 FROM leaves l
                    WHERE l.teacher_id = u.id AND l.is_substitution IS TRUE
                )
                """
            )

            # absences
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS absences (
                    id SERIAL PRIMARY KEY,
                    teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    date DATE NOT NULL,
                    hours_mask INTEGER NOT NULL DEFAULT 0,
                    note TEXT,
                    category TEXT,
                    CONSTRAINT uq_absences_teacher_date UNIQUE (teacher_id, date)
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_absences_teacher_id ON absences (teacher_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_absences_date ON absences (date)")

            # action_logs
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS action_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    action TEXT NOT NULL,
                    entity TEXT,
                    entity_id INTEGER,
                    detail TEXT,
                    module TEXT NOT NULL DEFAULT 'ausencias',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_action_logs_user_id ON action_logs (user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_action_logs_action ON action_logs (action)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_action_logs_created_at ON action_logs (created_at)"
            )
            cur.execute(
                """
                ALTER TABLE action_logs
                ADD COLUMN IF NOT EXISTS module TEXT NOT NULL DEFAULT 'ausencias'
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_action_logs_module ON action_logs (module)"
            )


def list_schedule_slots(*, teacher_id: int) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    teacher_id,
                    day_index,
                    hour_index,
                    type AS slot_type,
                    guard_type,
                    "group",
                    room,
                    subject,
                    source
                FROM schedule_slots
                WHERE teacher_id = %s
                ORDER BY day_index, hour_index, id
                """,
                (teacher_id,),
            )
            return list(cur.fetchall())


def list_schedule_slots_for_weekday(*, day_index: int) -> list[dict]:
    """Todos los slots del día lectivo ``day_index`` (0=lunes … 4=viernes), todos los profesores."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    teacher_id,
                    day_index,
                    hour_index,
                    type AS slot_type,
                    guard_type,
                    "group",
                    room,
                    subject
                FROM schedule_slots
                WHERE day_index = %s
                ORDER BY hour_index, teacher_id, id
                """,
                (day_index,),
            )
            return list(cur.fetchall())


def list_absences_range(
    *,
    from_date: date,
    to_date: date,
    uncategorized_only: bool = False,
) -> list[dict]:
    extra = ""
    params: list = [from_date, to_date]
    if uncategorized_only:
        extra = " AND COALESCE(TRIM(a.category), '') = '' "
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    a.id,
                    a.teacher_id,
                    u.name AS teacher_name,
                    a.date,
                    a.hours_mask,
                    a.note,
                    a.category
                FROM absences a
                JOIN users u ON u.id = a.teacher_id
                WHERE a.date >= %s AND a.date <= %s
                {extra}
                ORDER BY a.date DESC, a.id DESC
                """,
                tuple(params),
            )
            rows = list(cur.fetchall())
    rows.sort(
        key=lambda r: (
            -_date_ord(r["date"]),
            normalize_for_sort(str(r.get("teacher_name") or "")),
            -int(r["id"]),
        )
    )
    return rows


def list_active_teachers() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email, role, status, titular
                FROM users
                WHERE active = 1
                  AND COALESCE(status, 'activo') = 'activo'
                """
            )
            rows = list(cur.fetchall())
    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    return rows


def list_teachers_available_for_absence(*, on_date: date) -> list[dict]:
    """
    Profesores elegibles para registrar ausencia un día dado: activos y sin baja raíz
    vigente (misma regla que la app antigua).
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.id, u.name, u.email, u.role, u.status, u.titular
                FROM users u
                WHERE u.active = 1
                  AND COALESCE(u.status, 'activo') = 'activo'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM leaves l
                    WHERE l.teacher_id = u.id
                      AND l.parent_leave_id IS NULL
                      AND l.start_date <= %s
                      AND (l.end_date IS NULL OR l.end_date >= %s)
                  )
                """,
                (on_date, on_date),
            )
            rows = list(cur.fetchall())
    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    return rows


def list_teachers_for_schedule_selector() -> list[dict]:
    """Todos los usuarios (admin horarios): permite revisar titulares en baja o inactivos."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email, role, status, titular, active
                FROM users
                """
            )
            rows = list(cur.fetchall())
    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    return rows


def upsert_absence(
    *,
    teacher_id: int,
    on_date: date,
    hours_mask: int,
    note: str,
    category: str | None = None,
) -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO absences (teacher_id, date, hours_mask, note, category)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (teacher_id, date)
                DO UPDATE SET
                    hours_mask = EXCLUDED.hours_mask,
                    note = EXCLUDED.note,
                    category = COALESCE(EXCLUDED.category, absences.category)
                RETURNING id
                """,
                (teacher_id, on_date, hours_mask, note, category),
            )
            row = cur.fetchone()
            return int(row["id"])


def get_absence_by_id(*, absence_id: int) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT a.id, a.teacher_id, u.name AS teacher_name, a.date, a.hours_mask, a.note, a.category
                FROM absences a
                JOIN users u ON u.id = a.teacher_id
                WHERE a.id = %s
                """,
                (absence_id,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def update_absence_by_id(
    *,
    absence_id: int,
    on_date: date,
    hours_mask: int,
    note: str,
    category: str | None,
) -> None:
    """Actualiza fecha, máscara horaria, causa y catalogación; no cambia el profesor."""
    cat_clean = (category or "").strip() or None
    note_clean = (note or "").strip()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT teacher_id, date FROM absences WHERE id = %s",
                (absence_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Ausencia no encontrada")
            tid = int(row["teacher_id"])
            old_date = row["date"]
            if not isinstance(old_date, date):
                old_date = date.fromisoformat(str(old_date)[:10])
            if on_date != old_date:
                cur.execute(
                    """
                    SELECT 1 FROM absences
                    WHERE teacher_id = %s AND date = %s AND id <> %s
                    LIMIT 1
                    """,
                    (tid, on_date, absence_id),
                )
                if cur.fetchone():
                    raise ValueError("Ya existe una ausencia para ese profesor en la fecha indicada")
            cur.execute(
                """
                UPDATE absences
                SET date = %s, hours_mask = %s, note = %s, category = %s
                WHERE id = %s
                """,
                (on_date, hours_mask, note_clean, cat_clean, absence_id),
            )


def update_absence_category(*, absence_id: int, category: str | None) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE absences
                SET category = %s
                WHERE id = %s
                """,
                ((category or "").strip() or None, absence_id),
            )


def delete_absence(*, absence_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM absences WHERE id = %s", (absence_id,))


def update_leave_category(*, leave_id: int, category: str | None) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE leaves
                SET category = %s
                WHERE id = %s AND is_substitution IS FALSE
                """,
                ((category or "").strip() or None, leave_id),
            )


def list_leaves_uncategorized_in_range(*, from_date: date, to_date: date) -> list[dict]:
    """Bajas no sustitución que solapan el rango y sin categoría asignada (Z ya cuenta como catalogada)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    l.id,
                    l.teacher_id,
                    u.name AS teacher_name,
                    l.parent_leave_id,
                    l.start_date,
                    l.end_date,
                    l.cause,
                    l.substitute_teacher_id,
                    l.substitute_start_date,
                    l.substitute_end_date,
                    us.name AS substitute_name,
                    l.category,
                    l.is_substitution,
                    COALESCE(NULLIF(TRIM(l.leave_kind), ''), 'baja') AS leave_kind
                FROM leaves l
                JOIN users u ON u.id = l.teacher_id
                LEFT JOIN users us ON us.id = l.substitute_teacher_id
                WHERE l.is_substitution IS FALSE
                  AND l.start_date <= %s
                  AND (l.end_date IS NULL OR l.end_date >= %s)
                  AND COALESCE(TRIM(l.category), '') = ''
                ORDER BY l.start_date DESC, l.id DESC
                """,
                (to_date, from_date),
            )
            rows = list(cur.fetchall())
    rows.sort(
        key=lambda r: (
            -_date_ord(r["start_date"]),
            normalize_for_sort(str(r.get("teacher_name") or "")),
            -int(r["id"]),
        )
    )
    return rows


def _subtree_teacher_ids(cur, root_leave_id: int) -> set[int]:
    cur.execute(
        """
        WITH RECURSIVE sub AS (
          SELECT id, teacher_id FROM leaves WHERE id = %s
          UNION ALL
          SELECT l.id, l.teacher_id FROM leaves l
          INNER JOIN sub ON l.parent_leave_id = sub.id
        )
        SELECT DISTINCT teacher_id FROM sub
        """,
        (root_leave_id,),
    )
    return {int(r["teacher_id"]) for r in cur.fetchall()}


def _subtree_leave_ids(cur, root_leave_id: int) -> list[int]:
    cur.execute(
        """
        WITH RECURSIVE sub AS (
          SELECT id FROM leaves WHERE id = %s
          UNION ALL
          SELECT l.id FROM leaves l INNER JOIN sub ON l.parent_leave_id = sub.id
        )
        SELECT id FROM sub
        """,
        (root_leave_id,),
    )
    return [int(r["id"]) for r in cur.fetchall()]


def get_leave_by_id(*, leave_id: int) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    l.id,
                    l.teacher_id,
                    u.name AS teacher_name,
                    l.parent_leave_id,
                    l.start_date,
                    l.end_date,
                    l.cause,
                    l.substitute_teacher_id,
                    l.substitute_start_date,
                    l.substitute_end_date,
                    l.category,
                    l.is_substitution,
                    COALESCE(NULLIF(TRIM(l.leave_kind), ''), 'baja') AS leave_kind
                FROM leaves l
                JOIN users u ON u.id = l.teacher_id
                WHERE l.id = %s
                """,
                (leave_id,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def update_leave_record(
    *,
    leave_id: int,
    start_date: date,
    end_date: date | None,
    cause: str,
    category: str | None,
    leave_kind: str | None,
) -> None:
    if end_date is not None and end_date < start_date:
        raise ValueError("La fecha de fin no puede ser anterior al inicio")
    kind = _normalize_leave_kind(leave_kind, default="baja")
    cause_clean = (cause or "").strip()
    cat_clean = (category or "").strip() or None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, is_substitution FROM leaves WHERE id = %s",
                (leave_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Baja no encontrada")
            if row["is_substitution"]:
                raise ValueError("No se puede editar este registro desde esta pantalla")
            cur.execute(
                """
                UPDATE leaves
                SET start_date = %s, end_date = %s, cause = %s, category = %s, leave_kind = %s
                WHERE id = %s
                """,
                (start_date, end_date, cause_clean, cat_clean, kind, leave_id),
            )
            teachers = _subtree_teacher_ids(cur, leave_id)
            for tid in teachers:
                _sync_user_leave_state(cur, tid, [])


def update_substitution_leave_dates(*, leave_id: int, start_date: date, end_date: date | None) -> None:
    """Actualiza solo fechas de una fila de sustitución (admin/director)."""
    if end_date is not None and end_date < start_date:
        raise ValueError("La fecha de fin no puede ser anterior al inicio")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, teacher_id, parent_leave_id, start_date, end_date, is_substitution
                FROM leaves WHERE id = %s
                """,
                (leave_id,),
            )
            row = cur.fetchone()
            if not row or not row["is_substitution"]:
                raise ValueError("Sustitución no encontrada")
            pid = row["parent_leave_id"]
            if pid is not None:
                cur.execute(
                    "SELECT start_date, end_date FROM leaves WHERE id = %s",
                    (int(pid),),
                )
                parent = cur.fetchone()
                if parent:
                    if start_date < parent["start_date"]:
                        raise ValueError("La sustitución no puede empezar antes que la baja o sustitución padre")
                    pe = parent["end_date"]
                    if pe is not None:
                        eff_end = end_date if end_date is not None else pe
                        if eff_end > pe:
                            raise ValueError(
                                "La sustitución no puede prolongarse más allá del fin del registro padre"
                            )
                        if end_date is None:
                            end_date = pe
            cur.execute(
                """
                UPDATE leaves SET start_date = %s, end_date = %s
                WHERE id = %s AND is_substitution IS TRUE
                """,
                (start_date, end_date, leave_id),
            )
            _sync_user_leave_state(cur, int(row["teacher_id"]), [])


def delete_leave_subtree(*, leave_id: int) -> None:
    """Elimina la fila y todo el subárbol descendiente (sustituciones enlazadas)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, is_substitution FROM leaves WHERE id = %s",
                (leave_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Baja no encontrada")
            if row["is_substitution"]:
                raise ValueError("No se puede borrar este registro desde esta pantalla")
            teachers = _subtree_teacher_ids(cur, leave_id)
            if not teachers:
                raise ValueError("Baja no encontrada")
            ids = _subtree_leave_ids(cur, leave_id)
            cur.execute("DELETE FROM leaves WHERE id = ANY(%s)", (ids,))
            for tid in teachers:
                _sync_user_leave_state(cur, tid, [])


def list_leaves(*, include_closed: bool = True) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            if include_closed:
                cur.execute(
                    """
                    SELECT
                        l.id,
                        l.teacher_id,
                        u.name AS teacher_name,
                        l.parent_leave_id,
                        l.start_date,
                        l.end_date,
                        l.cause,
                        l.substitute_teacher_id,
                        l.substitute_start_date,
                        l.substitute_end_date,
                        us.name AS substitute_name,
                        l.category,
                        l.is_substitution,
                        COALESCE(NULLIF(TRIM(l.leave_kind), ''), 'baja') AS leave_kind
                    FROM leaves l
                    JOIN users u ON u.id = l.teacher_id
                    LEFT JOIN users us ON us.id = l.substitute_teacher_id
                    ORDER BY l.start_date DESC, l.id DESC
                    """
                )
            else:
                cur.execute(
                    """
                    SELECT
                        l.id,
                        l.teacher_id,
                        u.name AS teacher_name,
                        l.parent_leave_id,
                        l.start_date,
                        l.end_date,
                        l.cause,
                        l.substitute_teacher_id,
                        l.substitute_start_date,
                        l.substitute_end_date,
                        us.name AS substitute_name,
                        l.category,
                        l.is_substitution,
                        COALESCE(NULLIF(TRIM(l.leave_kind), ''), 'baja') AS leave_kind
                    FROM leaves l
                    JOIN users u ON u.id = l.teacher_id
                    LEFT JOIN users us ON us.id = l.substitute_teacher_id
                    WHERE l.end_date IS NULL
                    ORDER BY l.start_date DESC, l.id DESC
                    """
                )
            rows = list(cur.fetchall())
    rows.sort(
        key=lambda r: (
            -_date_ord(r["start_date"]),
            normalize_for_sort(str(r.get("teacher_name") or "")),
            -int(r["id"]),
        )
    )
    return rows


def list_open_parent_leaves_without_active_substitution() -> list[dict]:
    """Bajas abiertas (titular o sustituto en cadena) sin sustituto activo debajo.

    - Titular p1 con sustituto s1 ya enlazado tiene una fila hija abierta → no se ofrece.
    - La fila de sustitución de s1 sin sustituto encima sigue ofreciéndose para enlazar s2.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    l.id,
                    l.teacher_id,
                    u.name AS teacher_name,
                    l.parent_leave_id,
                    l.start_date,
                    l.end_date,
                    l.cause,
                    l.substitute_teacher_id,
                    l.substitute_start_date,
                    l.substitute_end_date,
                    us.name AS substitute_name,
                    l.category,
                    l.is_substitution,
                    COALESCE(NULLIF(TRIM(l.leave_kind), ''), 'baja') AS leave_kind
                FROM leaves l
                JOIN users u ON u.id = l.teacher_id
                LEFT JOIN users us ON us.id = l.substitute_teacher_id
                WHERE l.end_date IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM leaves ch
                    WHERE ch.parent_leave_id = l.id
                      AND ch.end_date IS NULL
                  )
                """
            )
            rows = list(cur.fetchall())
    rows.sort(
        key=lambda r: (
            _date_ord(r["start_date"]),
            int(r["id"]),
        )
    )
    return rows


def _normalize_leave_kind(value: str | None, *, default: str = "baja") -> str:
    k = (value or default).strip().lower()
    return k if k in ("baja", "excedencia") else default


def _sync_user_leave_state(cur, teacher_id: int, closed_leave_ids: list[int]) -> None:
    """Deriva ``users.status`` y ``titular`` tras cerrar hojas (sin orden frágil fila a fila)."""
    tid = int(teacher_id)

    cur.execute(
        """
        SELECT 1 FROM leaves
        WHERE teacher_id = %s AND is_substitution IS TRUE AND end_date IS NULL
        LIMIT 1
        """,
        (tid,),
    )
    if cur.fetchone():
        cur.execute(
            "UPDATE users SET status = 'activo', titular = FALSE WHERE id = %s",
            (tid,),
        )
        return

    cur.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(leave_kind), ''), 'baja') AS leave_kind, parent_leave_id
        FROM leaves
        WHERE teacher_id = %s AND is_substitution IS FALSE AND end_date IS NULL
        ORDER BY start_date ASC, id ASC
        LIMIT 1
        """,
        (tid,),
    )
    row = cur.fetchone()
    if row:
        kind = str(row["leave_kind"] or "baja").strip().lower()
        if kind not in ("baja", "excedencia"):
            kind = "baja"
        status = "excedencia" if kind == "excedencia" else "baja"
        is_root = row["parent_leave_id"] is None
        cur.execute(
            "UPDATE users SET status = %s, titular = %s WHERE id = %s",
            (status, is_root, tid),
        )
        return

    if closed_leave_ids:
        cur.execute(
            """
            SELECT MAX(CASE WHEN is_substitution THEN 1 ELSE 0 END) AS mx
            FROM leaves
            WHERE id = ANY(%s) AND teacher_id = %s
            """,
            (closed_leave_ids, tid),
        )
        r2 = cur.fetchone()
        if r2 and int(r2["mx"] or 0) >= 1:
            cur.execute(
                "UPDATE users SET status = 'exprofe', titular = FALSE WHERE id = %s",
                (tid,),
            )
            cur.execute(
                "DELETE FROM schedule_slots WHERE teacher_id = %s AND source LIKE 'substitution:%%'",
                (tid,),
            )
            return

    cur.execute(
        """
        SELECT 1 FROM leaves
        WHERE teacher_id = %s AND is_substitution IS TRUE
        LIMIT 1
        """,
        (tid,),
    )
    ever_substitute = cur.fetchone() is not None
    cur.execute(
        "UPDATE users SET status = 'activo', titular = %s WHERE id = %s",
        (not ever_substitute, tid),
    )


def create_leave_root(
    *,
    teacher_id: int,
    start_date: date,
    cause: str,
    category: str | None = None,
    leave_kind: str | None = None,
) -> int:
    kind_nested = "baja"
    kind_root = _normalize_leave_kind(leave_kind, default="baja")
    status_root = "excedencia" if kind_root == "excedencia" else "baja"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM leaves
                WHERE teacher_id = %s
                  AND parent_leave_id IS NOT NULL
                  AND end_date IS NULL
                ORDER BY start_date DESC, id DESC
                LIMIT 1
                """,
                (teacher_id,),
            )
            active_sub = cur.fetchone()
            if active_sub:
                cur.execute(
                    """
                    INSERT INTO leaves (
                        teacher_id, parent_leave_id, start_date, cause, category, is_substitution, leave_kind
                    )
                    VALUES (%s, %s, %s, %s, %s, FALSE, %s)
                    RETURNING id
                    """,
                    (
                        teacher_id,
                        int(active_sub["id"]),
                        start_date,
                        (cause or "").strip(),
                        category,
                        kind_nested,
                    ),
                )
                leave_id = int(cur.fetchone()["id"])
                cur.execute(
                    """
                    UPDATE users
                    SET status = 'baja', titular = FALSE
                    WHERE id = %s
                    """,
                    (teacher_id,),
                )
                return leave_id

            cur.execute(
                """
                SELECT 1
                FROM leaves
                WHERE teacher_id = %s
                  AND parent_leave_id IS NULL
                  AND end_date IS NULL
                LIMIT 1
                """,
                (teacher_id,),
            )
            if cur.fetchone():
                raise ValueError("Este profesor ya tiene una baja activa")

            cur.execute(
                """
                INSERT INTO leaves (
                    teacher_id, parent_leave_id, start_date, cause, category, is_substitution, leave_kind
                )
                VALUES (%s, NULL, %s, %s, %s, FALSE, %s)
                RETURNING id
                """,
                (teacher_id, start_date, (cause or "").strip(), category, kind_root),
            )
            leave_id = int(cur.fetchone()["id"])
            cur.execute(
                """
                UPDATE users
                SET status = %s, titular = TRUE
                WHERE id = %s
                """,
                (status_root, teacher_id),
            )
            return leave_id


def _get_descendant_leave_ids(cur, root_leave_id: int) -> list[int]:
    pending = [root_leave_id]
    all_ids: list[int] = []
    while pending:
        current = pending.pop()
        cur.execute("SELECT id FROM leaves WHERE parent_leave_id = %s", (current,))
        children = [int(r["id"]) for r in cur.fetchall()]
        all_ids.extend(children)
        pending.extend(children)
    return all_ids


def close_leave(*, leave_id: int, end_date: date, mode: str = "cascade") -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, teacher_id, parent_leave_id, start_date, end_date FROM leaves WHERE id = %s",
                (leave_id,),
            )
            lv = cur.fetchone()
            if not lv:
                raise ValueError("La baja no existe")
            if lv["end_date"] is not None:
                raise ValueError("La baja ya estaba cerrada")
            if end_date < lv["start_date"]:
                raise ValueError("Fecha de cierre inválida")

            if mode not in {"cascade", "subtree"}:
                mode = "cascade"
            leaves_to_close = [leave_id]
            leaves_to_close.extend(_get_descendant_leave_ids(cur, leave_id))

            cur.execute(
                """
                UPDATE leaves
                SET end_date = %s, substitute_teacher_id = NULL, substitute_end_date = %s
                WHERE id = ANY(%s)
                """,
                (end_date, end_date, leaves_to_close),
            )

            if mode == "subtree" and lv["parent_leave_id"] is not None:
                cur.execute(
                    "UPDATE leaves SET substitute_teacher_id = NULL, substitute_end_date = %s WHERE id = %s",
                    (end_date, lv["parent_leave_id"]),
                )

            cur.execute(
                "SELECT id, teacher_id FROM leaves WHERE id = ANY(%s)",
                (leaves_to_close,),
            )
            by_teacher: dict[int, list[int]] = {}
            for row in cur.fetchall():
                lid, tid = int(row["id"]), int(row["teacher_id"])
                by_teacher.setdefault(tid, []).append(lid)

            for tid, lids in by_teacher.items():
                _sync_user_leave_state(cur, tid, lids)


def finalize_baja_leave(*, leave_id: int, end_date: date) -> None:
    """Cierra una fila de baja/excedencia (no sustitución) y todo el subárbol descendiente.

    Usa modo ``subtree`` para cerrar la cadena y actualizar enlaces en el padre cuando procede.
    Los sustitutos cuya sustitución queda cerrada pasan a ``exprofe`` vía ``_sync_user_leave_state``.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, is_substitution, end_date, start_date
                FROM leaves WHERE id = %s
                """,
                (leave_id,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("La baja no existe")
            if row["end_date"] is not None:
                raise ValueError("La baja ya estaba cerrada")
            if row["is_substitution"]:
                raise ValueError("Las sustituciones se finalizan desde Finalizar sustitución")
            if end_date < row["start_date"]:
                raise ValueError("La fecha de fin no puede ser anterior al inicio")
    close_leave(leave_id=leave_id, end_date=end_date, mode="subtree")


def list_teachers_eligible_substitution_resign_finish() -> list[dict]:
    """Activos, no titulares, con sustitución abierta en la punta de la cadena (nadie les sustituye aún)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT u.id, u.name, u.email, u.role, u.status, u.titular
                FROM users u
                INNER JOIN leaves l ON l.teacher_id = u.id
                  AND l.is_substitution IS TRUE
                  AND l.end_date IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM leaves ch
                    WHERE ch.parent_leave_id = l.id AND ch.end_date IS NULL
                  )
                WHERE u.active = 1
                  AND COALESCE(u.status, 'activo') = 'activo'
                  AND u.titular IS FALSE
                """
            )
            rows = list(cur.fetchall())
    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    return rows


def _fetch_open_leaf_substitution_leave_row(cur, teacher_id: int) -> tuple[int, date] | None:
    tid = int(teacher_id)
    cur.execute(
        """
        SELECT l.id, l.start_date FROM leaves l
        WHERE l.teacher_id = %s
          AND l.is_substitution IS TRUE
          AND l.end_date IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM leaves ch
            WHERE ch.parent_leave_id = l.id AND ch.end_date IS NULL
          )
        ORDER BY l.id DESC
        LIMIT 1
        """,
        (tid,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return int(row["id"]), row["start_date"]


def finalize_substitution_resignation(*, substitute_teacher_id: int, end_date: date) -> int:
    """Cierra la sustitución por renuncia al encargo (solo hoja de cadena). Devuelve leave_id cerrado."""
    tid = int(substitute_teacher_id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, titular, COALESCE(status, 'activo') AS st, active
                FROM users WHERE id = %s
                """,
                (tid,),
            )
            u = cur.fetchone()
            if not u or int(u.get("active") or 0) != 1:
                raise ValueError("Profesor no válido o inactivo")
            if str(u.get("st") or "").strip().lower() != "activo":
                raise ValueError("El profesor debe estar en estado activo")
            if bool(u["titular"]):
                raise ValueError("Solo aplica a profesores no titulares")
            leaf = _fetch_open_leaf_substitution_leave_row(cur, tid)
            if not leaf:
                raise ValueError("No hay sustitución abierta en punta de cadena para ese profesor")
            lid, start = leaf
            if end_date < start:
                raise ValueError("La fecha de fin no puede ser anterior al inicio")
    close_leave(leave_id=lid, end_date=end_date, mode="subtree")
    return lid


def list_available_substitute_teachers(*, for_leave_id: int) -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT teacher_id FROM leaves WHERE id = %s", (for_leave_id,))
            root = cur.fetchone()
            if not root:
                return []
            cur.execute(
                """
                SELECT id, name, email, role, status, titular
                FROM users
                WHERE active = 1
                  AND COALESCE(status, 'activo') = 'activo'
                  AND id <> %s
                """,
                (root["teacher_id"],),
            )
            rows = list(cur.fetchall())
    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    return rows


def list_exprofes_for_substitution() -> list[dict]:
    """Profesorado activo en estado exprofe (reincorporable como sustituto)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email
                FROM users
                WHERE active = 1
                  AND LOWER(TRIM(COALESCE(status, ''))) = 'exprofe'
                """
            )
            rows = list(cur.fetchall())
    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    return [
        {"id": int(r["id"]), "name": str(r.get("name") or ""), "email": str(r.get("email") or "")}
        for r in rows
    ]


def create_substitution(*, leave_id: int, substitute_teacher_id: int, start_date: date) -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, teacher_id, start_date, end_date FROM leaves WHERE id = %s", (leave_id,))
            parent = cur.fetchone()
            if not parent or parent["end_date"] is not None:
                raise ValueError("Baja no válida para sustitución")
            if start_date < parent["start_date"]:
                raise ValueError("La sustitución no puede empezar antes de la baja")
            cur.execute("SELECT 1 FROM leaves WHERE parent_leave_id = %s AND end_date IS NULL LIMIT 1", (leave_id,))
            if cur.fetchone():
                raise ValueError("La baja ya tiene una sustitución activa")
            cur.execute("SELECT 1 FROM leaves WHERE teacher_id = %s AND end_date IS NULL LIMIT 1", (substitute_teacher_id,))
            if cur.fetchone():
                raise ValueError("El sustituto seleccionado ya tiene una baja activa")
            cur.execute(
                """
                SELECT id FROM users
                WHERE id = %s AND active = 1
                  AND LOWER(TRIM(COALESCE(status, 'activo'))) IN ('activo', 'exprofe')
                LIMIT 1
                """,
                (substitute_teacher_id,),
            )
            if not cur.fetchone():
                raise ValueError("Sustituto no válido")
            cur.execute(
                """
                INSERT INTO leaves (
                    teacher_id, parent_leave_id, start_date, cause, category, is_substitution, leave_kind
                )
                VALUES (%s, %s, %s, 'Sustitución', NULL, TRUE, 'baja')
                RETURNING id
                """,
                (substitute_teacher_id, leave_id, start_date),
            )
            child_id = int(cur.fetchone()["id"])
            cur.execute(
                """
                UPDATE leaves
                SET substitute_teacher_id = %s, substitute_start_date = %s, substitute_end_date = NULL
                WHERE id = %s
                """,
                (substitute_teacher_id, start_date, leave_id),
            )
            cur.execute(
                "SELECT tutor, departamento FROM users WHERE id = %s",
                (int(parent["teacher_id"]),),
            )
            replaced = cur.fetchone() or {}
            tutor_inherited = (replaced.get("tutor") or "").strip() or None
            dept_inherited = (replaced.get("departamento") or "").strip() or None
            cur.execute(
                """
                UPDATE users
                SET status = 'activo', titular = FALSE, tutor = %s, departamento = %s
                WHERE id = %s
                """,
                (tutor_inherited, dept_inherited, substitute_teacher_id),
            )
            cur.execute("SELECT day_index, hour_index FROM schedule_slots WHERE teacher_id = %s", (parent["teacher_id"],))
            for row in cur.fetchall():
                cur.execute(
                    "DELETE FROM schedule_slots WHERE teacher_id = %s AND day_index = %s AND hour_index = %s",
                    (substitute_teacher_id, int(row["day_index"]), int(row["hour_index"])),
                )
            cur.execute(
                """
                INSERT INTO schedule_slots (teacher_id, day_index, hour_index, type, guard_type, "group", room, subject, source)
                SELECT %s, s.day_index, s.hour_index, s.type, s.guard_type, s."group", s.room, s.subject, %s
                FROM schedule_slots s
                WHERE s.teacher_id = %s
                """,
                (substitute_teacher_id, f"substitution:{parent['teacher_id']}", parent["teacher_id"]),
            )
            return child_id


def add_action_log(*args, **kwargs):
    from db.action_logs import add_action_log as _add

    return _add(*args, **kwargs)


def has_open_leave(*, teacher_id: int) -> bool:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM leaves WHERE teacher_id = %s AND end_date IS NULL LIMIT 1", (teacher_id,))
            return cur.fetchone() is not None


def list_action_logs(*args, **kwargs):
    from db.action_logs import list_action_logs as _list

    return _list(*args, **kwargs)


def upsert_teacher_from_import(
    *,
    name: str,
    email: str,
    alias: str | None = None,
    role: str | None = None,
    status: str | None = None,
    titular: bool | None = None,
    active: bool | None = None,
) -> str:
    clean_name = (name or "").strip()
    clean_email = (email or "").strip().lower()
    if not clean_name or not clean_email:
        raise ValueError("Nombre y email son obligatorios")
    role_v = (role or "profesor").strip().lower() or "profesor"
    status_v = (status or "activo").strip().lower() or "activo"
    alias_v = (alias or "").strip() or clean_name
    titular_v = True if titular is None else bool(titular)
    active_v = 1 if (True if active is None else bool(active)) else 0
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (clean_email,))
            row = cur.fetchone()
            if row:
                cur.execute(
                    """
                    UPDATE users
                    SET name = %s, alias = %s, role = %s, status = %s, titular = %s, active = %s
                    WHERE id = %s
                    """,
                    (clean_name, alias_v, role_v, status_v, titular_v, active_v, row["id"]),
                )
                return "updated"
            cur.execute(
                """
                INSERT INTO users (name, email, role, alias, status, titular, active, must_change_password)
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
                """,
                (clean_name, clean_email, role_v, alias_v, status_v, titular_v, active_v),
            )
            return "created"


def list_teachers_min() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email, alias
                FROM users
                WHERE active = 1
                """
            )
            rows = list(cur.fetchall())
    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    return rows


def clear_schedule_cell(*, teacher_id: int, day_index: int, hour_index: int) -> None:
    """Elimina cualquier clase o guardia en esa celda (un único slot por día/franja)."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM schedule_slots WHERE teacher_id = %s AND day_index = %s AND hour_index = %s",
                (teacher_id, day_index, hour_index),
            )


def replace_schedule_slot(
    *,
    teacher_id: int,
    day_index: int,
    hour_index: int,
    slot_type: str,
    guard_type: str | None = None,
    group_name: str | None = None,
    room: str | None = None,
    subject: str | None = None,
    source: str = "import",
) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM schedule_slots WHERE teacher_id = %s AND day_index = %s AND hour_index = %s",
                (teacher_id, day_index, hour_index),
            )
            cur.execute(
                """
                INSERT INTO schedule_slots (teacher_id, day_index, hour_index, type, guard_type, "group", room, subject, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    teacher_id,
                    day_index,
                    hour_index,
                    slot_type,
                    (guard_type or "").strip() or None,
                    (group_name or "").strip() or None,
                    (room or "").strip() or None,
                    (subject or "").strip() or None,
                    source,
                ),
            )


def apply_teacher_schedule_grid_edits(*, teacher_id: int, cells: list[dict]) -> None:
    """Igual que 35× ``replace_schedule_slot`` pero en **una transacción** (mismo SQL por celda).

    Por celda: ``DELETE`` de ese día/franja y, si no es vacío, ``INSERT`` con los mismos
    nulos opcionales que el import Excel.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            for c in cells:
                di = int(c["day_index"])
                hi = int(c["hour_index"])
                kind = str(c.get("kind") or "NONE").upper()
                cur.execute(
                    "DELETE FROM schedule_slots WHERE teacher_id = %s AND day_index = %s AND hour_index = %s",
                    (teacher_id, di, hi),
                )
                if kind == "NONE":
                    continue
                if kind == "CLASS":
                    g = (str(c.get("group") or "").strip() or None)
                    room = (str(c.get("room") or "").strip() or None)
                    sub = (str(c.get("subject") or "").strip() or None)
                    if not g and not sub:
                        continue
                    cur.execute(
                        """
                        INSERT INTO schedule_slots (teacher_id, day_index, hour_index, type, guard_type, "group", room, subject, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (teacher_id, di, hi, "CLASS", None, g, room, sub, "manual_edit"),
                    )
                elif kind == "GUARD":
                    gt = (str(c.get("guard_type") or "").strip() or None)
                    if not gt:
                        continue
                    cur.execute(
                        """
                        INSERT INTO schedule_slots (teacher_id, day_index, hour_index, type, guard_type, "group", room, subject, source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (teacher_id, di, hi, "GUARD", gt, None, None, None, "manual_edit"),
                    )

