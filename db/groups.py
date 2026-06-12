from __future__ import annotations

from db.connection import get_db
from utils.text import normalize_for_sort


def ensure_groups_schema() -> None:
    """Crea tabla/índice de grupos si no existen."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS groups (
                    name TEXT PRIMARY KEY,
                    curso TEXT
                )
                """
            )
            cur.execute("ALTER TABLE groups ADD COLUMN IF NOT EXISTS curso TEXT")
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_groups_name_lower
                ON groups (LOWER(name))
                """
            )


def list_groups() -> list[str]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name
                FROM groups
                WHERE name IS NOT NULL
                  AND btrim(name) <> ''
                """
            )
            rows = cur.fetchall()

    names = [str(r["name"]).strip() for r in rows if r.get("name")]
    names.sort(key=normalize_for_sort)
    return names


def list_distinct_cursos() -> list[str]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT curso
                FROM groups
                WHERE curso IS NOT NULL AND btrim(curso) <> ''
                ORDER BY curso
                """
            )
            return [str(r["curso"]).strip() for r in cur.fetchall() if r.get("curso")]


def list_group_names_for_curso(curso: str | None = None) -> list[str]:
    curso_clean = (curso or "").strip() or None
    with get_db() as conn:
        with conn.cursor() as cur:
            if curso_clean:
                cur.execute(
                    """
                    SELECT name
                    FROM groups
                    WHERE curso IS NOT NULL
                      AND btrim(curso) <> ''
                      AND LOWER(TRIM(curso)) = LOWER(TRIM(%s))
                    ORDER BY name
                    """,
                    (curso_clean,),
                )
            else:
                cur.execute(
                    """
                    SELECT name
                    FROM groups
                    WHERE name IS NOT NULL AND btrim(name) <> ''
                    ORDER BY name
                    """
                )
            return [str(r["name"]).strip() for r in cur.fetchall() if r.get("name")]


def list_groups_with_course() -> list[dict]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name, curso
                FROM groups
                WHERE name IS NOT NULL
                  AND btrim(name) <> ''
                """
            )
            rows = cur.fetchall()

    items = [
        {
            "name": str(r["name"]).strip(),
            "curso": (str(r["curso"]).strip() if r.get("curso") is not None else ""),
        }
        for r in rows
        if r.get("name")
    ]
    items.sort(key=lambda r: normalize_for_sort(r["name"]))
    return items


def upsert_group_name(name: str, curso: str | None = None) -> bool:
    """
    Inserta grupo por nombre (case-insensitive).
    Devuelve True si crea; False si ya existía.
    """
    clean = (name or "").strip()
    curso_clean = (curso or "").strip() or None
    if not clean:
        raise ValueError("El nombre del grupo es obligatorio")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name
                FROM groups
                WHERE LOWER(BTRIM(name)) = LOWER(%s)
                LIMIT 1
                """,
                (clean,),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE groups
                    SET curso = %s
                    WHERE LOWER(BTRIM(name)) = LOWER(%s)
                    """,
                    (curso_clean, clean),
                )
                return False

            cur.execute(
                """
                INSERT INTO groups (name, curso)
                VALUES (%s, %s)
                """,
                (clean, curso_clean),
            )
            return True


def get_group_curso(name: str) -> str | None:
    from utils.group_stage import normalize_group_name

    for candidate in (
        (name or "").strip(),
        normalize_group_name(name),
    ):
        if not candidate:
            continue
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT curso
                    FROM groups
                    WHERE LOWER(BTRIM(name)) = LOWER(%s)
                    LIMIT 1
                    """,
                    (candidate,),
                )
                row = cur.fetchone()
        if row and row.get("curso") is not None:
            curso = str(row["curso"]).strip()
            if curso:
                return curso
    return None


def group_exists(name: str) -> bool:
    clean = (name or "").strip()
    if not clean:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM groups
                WHERE LOWER(BTRIM(name)) = LOWER(%s)
                LIMIT 1
                """,
                (clean,),
            )
            return cur.fetchone() is not None
