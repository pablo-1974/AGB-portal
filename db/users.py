# db/users.py — acceso a la tabla users (portal compartido)
from __future__ import annotations

from psycopg.errors import UniqueViolation

from db.connection import get_db
from security.passwords import hash_password
from utils.text import normalize_for_sort

_USER_COLUMNS = """
    id, name, email, role, alias, status, titular, tutor, departamento,
    password_hash, active, must_change_password, created_at, created_by, last_login_at,
    login_failed_count, login_locked
"""


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _row_to_user(row: dict | None) -> dict | None:
    if not row:
        return None
    return dict(row)


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_USER_COLUMNS}
                FROM users
                WHERE id = %s
                """,
                (int(user_id),),
            )
            return _row_to_user(cur.fetchone())


def get_user_by_email(email: str) -> dict | None:
    clean = _normalize_email(email)
    if not clean:
        return None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_USER_COLUMNS}
                FROM users
                WHERE LOWER(email) = %s
                """,
                (clean,),
            )
            return _row_to_user(cur.fetchone())


def has_any_user() -> bool:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users LIMIT 1")
            return cur.fetchone() is not None


def create_first_admin(*, name: str, email: str, password: str) -> None:
    clean_name = (name or "").strip()
    clean_email = _normalize_email(email)
    if not clean_name or not clean_email or not password:
        raise ValueError("Nombre, email y contraseña son obligatorios")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (
                    name, email, role, password_hash, active, must_change_password
                )
                VALUES (%s, %s, 'admin', %s, 1, FALSE)
                """,
                (clean_name, clean_email, hash_password(password)),
            )


def _insert_user_admin(
    cur,
    *,
    name: str,
    email: str,
    role: str,
    created_by: int | None,
    alias: str | None = None,
    status: str | None = None,
    titular: bool = True,
    tutor: str | None = None,
    departamento: str | None = None,
    active: int = 1,
    returning_id: bool = False,
) -> int | None:
    clean_name = (name or "").strip()
    clean_email = _normalize_email(email)
    role_v = (role or "").strip().lower()
    if not clean_name or not clean_email or not role_v:
        raise ValueError("Nombre, email y rol son obligatorios")

    status_v = (status or "activo").strip() or "activo"
    alias_v = (alias or "").strip() or None
    tutor_v = (tutor or "").strip() or None
    dept_v = (departamento or "").strip() or None
    active_v = 1 if int(active) else 0

    sql = """
        INSERT INTO users (
            name, email, role, alias, status, titular, tutor, departamento,
            password_hash, active, must_change_password, created_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, TRUE, %s)
    """
    params = (
        clean_name,
        clean_email,
        role_v,
        alias_v,
        status_v,
        bool(titular),
        tutor_v,
        dept_v,
        active_v,
        created_by,
    )
    if returning_id:
        cur.execute(sql + " RETURNING id", params)
        row = cur.fetchone()
        return int(row["id"]) if row else None
    cur.execute(sql, params)
    return None


def create_user_admin(
    *,
    name: str,
    email: str,
    role: str,
    created_by: int | None,
    alias: str | None = None,
    status: str | None = None,
    titular: bool = True,
    tutor: str | None = None,
    departamento: str | None = None,
) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            try:
                _insert_user_admin(
                    cur,
                    name=name,
                    email=email,
                    role=role,
                    created_by=created_by,
                    alias=alias,
                    status=status,
                    titular=titular,
                    tutor=tutor,
                    departamento=departamento,
                )
            except UniqueViolation:
                raise


def create_user_admin_returning_id(
    *,
    name: str,
    email: str,
    role: str,
    created_by: int | None,
    alias: str | None = None,
    status: str | None = None,
    titular: bool = True,
    tutor: str | None = None,
    departamento: str | None = None,
    active: int = 1,
) -> int:
    with get_db() as conn:
        with conn.cursor() as cur:
            try:
                new_id = _insert_user_admin(
                    cur,
                    name=name,
                    email=email,
                    role=role,
                    created_by=created_by,
                    alias=alias,
                    status=status,
                    titular=titular,
                    tutor=tutor,
                    departamento=departamento,
                    active=active,
                    returning_id=True,
                )
            except UniqueViolation:
                raise
    if new_id is None:
        raise ValueError("No se pudo crear el usuario")
    return new_id


def update_user_admin(
    *,
    user_id: int,
    name: str,
    email: str,
    role: str,
    alias: str | None = None,
    status: str | None = None,
    titular: bool = True,
    tutor: str | None = None,
    departamento: str | None = None,
    set_departamento: bool = False,
) -> None:
    clean_name = (name or "").strip()
    clean_email = _normalize_email(email)
    role_v = (role or "").strip().lower()
    if not clean_name or not clean_email or not role_v:
        raise ValueError("Nombre, email y rol son obligatorios")

    status_v = (status or "activo").strip() or "activo"
    alias_v = (alias or "").strip() or None
    tutor_v = (tutor or "").strip() or None
    if not set_departamento:
        dept_sql = ""
        dept_params: tuple = ()
    else:
        dept_sql = ", departamento = %s"
        dept_params = ((departamento or "").strip() or None,)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE users
                SET name = %s,
                    email = %s,
                    role = %s,
                    alias = %s,
                    status = %s,
                    titular = %s,
                    tutor = %s
                    {dept_sql}
                WHERE id = %s
                """,
                (
                    clean_name,
                    clean_email,
                    role_v,
                    alias_v,
                    status_v,
                    bool(titular),
                    tutor_v,
                    *dept_params,
                    int(user_id),
                ),
            )


def set_user_active(*, user_id: int, active: bool) -> None:
    active_v = 1 if active else 0
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET active = %s WHERE id = %s",
                (active_v, int(user_id)),
            )


def reset_user_password(*, user_id: int) -> None:
    from db.login_security import unlock_user_login

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET password_hash = NULL, must_change_password = TRUE
                WHERE id = %s
                """,
                (int(user_id),),
            )
    unlock_user_login(user_id)


def set_user_password(*, user_id: int, password_hash: str) -> None:
    from db.login_security import clear_user_login_failures, unlock_user_login

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET password_hash = %s, must_change_password = FALSE
                WHERE id = %s
                """,
                (password_hash, int(user_id)),
            )
    clear_user_login_failures(user_id)
    unlock_user_login(user_id)


def update_last_login(*, user_id: int) -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET last_login_at = now()
                WHERE id = %s
                """,
                (int(user_id),),
            )


def get_all_users() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {_USER_COLUMNS}
                FROM users
                ORDER BY id
                """
            )
            rows = [dict(r) for r in cur.fetchall()]
    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    return rows


def get_all_teachers() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email, role, status, titular
                FROM users
                WHERE active = 1
                  AND COALESCE(status, 'activo') = 'activo'
                  AND LOWER(TRIM(COALESCE(role, ''))) <> 'invitado'
                """
            )
            rows = [dict(r) for r in cur.fetchall()]
    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    return rows


def get_all_professors_cuadro() -> list[dict]:
    """Todos los usuarios (cualquier rol, status y activo/inactivo) para filtros del cuadro."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, alias, status, active, role
                FROM users
                """
            )
            rows = list(cur.fetchall())
    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    out: list[dict] = []
    for r in rows:
        name = str(r.get("name") or "").strip()
        alias = (str(r.get("alias") or "").strip() or name)
        out.append(
            {
                "id": int(r["id"]),
                "name": name,
                "alias": alias,
                "label": name,
                "role": str(r.get("role") or "").strip(),
                "status": str(r.get("status") or ""),
                "active": int(r.get("active") or 0),
            }
        )
    return out


def get_all_active_users_basic() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name
                FROM users
                WHERE active = 1
                ORDER BY id
                """
            )
            rows = [dict(r) for r in cur.fetchall()]
    rows.sort(key=lambda r: normalize_for_sort(str(r.get("name") or "")))
    return rows
