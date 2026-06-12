"""Consultas para listados de profesorado en ``/listados/profesores`` (todos los usuarios que cumplen criterio)."""



from __future__ import annotations



from typing import Any



from ausencias.db import list_leaves

from db.connection import get_db

from utils.text import normalize_for_sort





def _root_absent_teacher_name(by_id: dict[int, dict], leaf_id: int) -> str | None:

    """Nombre del profesor en la baja raíz (inicio de cadena) desde una fila sustitución."""

    cur: dict | None = by_id.get(leaf_id)

    if not cur:

        return None

    seen: set[int] = set()

    while cur is not None:

        cid = int(cur["id"])

        if cid in seen:

            return None

        seen.add(cid)

        pid = cur.get("parent_leave_id")

        if pid is None:

            return str(cur.get("teacher_name") or "").strip() or None

        parent = by_id.get(int(pid))

        if parent is None:

            return str(cur.get("teacher_name") or "").strip() or None

        if not parent.get("is_substitution"):

            return str(parent.get("teacher_name") or "").strip() or None

        cur = parent

    return None





def substitute_to_root_absent_name_map() -> dict[int, str]:

    """Sustituto (``teacher_id`` de fila sustitución abierta) → nombre en la baja raíz."""

    rows = list_leaves(include_closed=False)

    by_id: dict[int, dict] = {int(r["id"]): r for r in rows}

    out: dict[int, str] = {}

    for r in rows:

        if not r.get("is_substitution"):

            continue

        if r.get("end_date") is not None:

            continue

        tid = int(r["teacher_id"])

        lid = int(r["id"])

        root = _root_absent_teacher_name(by_id, lid)

        if root and tid not in out:

            out[tid] = root

    return out





def _sort_prof_rows(rows: list[dict], *, name_key: str = "name") -> list[dict]:

    return sorted(rows, key=lambda r: normalize_for_sort(str(r.get(name_key) or "")))





def list_distinct_profesor_departamentos() -> list[str]:

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT DISTINCT TRIM(u.departamento) AS d

                FROM users AS u

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





def _fetch_profesores_base_sql(extra_where: str, params: tuple[Any, ...]) -> list[dict]:

    """Usuarios que cumplen ``extra_where``; sin filtrar por rol."""

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                f"""

                SELECT u.id, u.name, u.email, u.status, u.titular, u.tutor, u.departamento, u.active

                FROM users AS u

                WHERE TRUE

                  {extra_where}

                """,

                params,

            )

            return list(cur.fetchall())





def list_profesorado_inicial_titulares() -> list[dict]:

    rows = _fetch_profesores_base_sql(

        "AND u.titular IS TRUE AND u.active = 1 AND LOWER(TRIM(COALESCE(u.status, 'activo'))) = 'activo'",

        (),

    )

    return _sort_prof_rows([{"name": r["name"], "email": r.get("email")} for r in rows])





def list_profesorado_sustitutos() -> list[dict]:

    rows = _fetch_profesores_base_sql("AND u.titular = FALSE", ())

    return _sort_prof_rows([{"name": r["name"], "email": r.get("email")} for r in rows])





def list_profesorado_todos_con_estado() -> list[dict]:

    rows = _fetch_profesores_base_sql("", ())

    out: list[dict] = []

    for r in rows:

        st = str(r.get("status") or "").strip() or "—"

        nm = str(r.get("name") or "").strip()

        out.append({"name": f"{nm} ({st})", "email": r.get("email")})

    return _sort_prof_rows(out, name_key="name")





def list_profesorado_activos_con_cadena() -> list[dict]:

    """Usuarios activos (estado activo); no titulares con sustitución abierta muestran titular raíz entre paréntesis."""

    rows = _fetch_profesores_base_sql(

        "AND u.active = 1 AND LOWER(TRIM(COALESCE(u.status, 'activo'))) = 'activo'",

        (),

    )

    chain = substitute_to_root_absent_name_map()

    out: list[dict] = []

    for r in rows:

        nm = str(r.get("name") or "").strip()

        tid = int(r["id"])

        titular = bool(r.get("titular"))

        if not titular:

            root = chain.get(tid)

            if root:

                nm = f"{nm} ({root})"

        out.append({"name": nm, "email": r.get("email")})

    return _sort_prof_rows(out, name_key="name")





def list_tutores_rows() -> list[dict]:

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT u.name, u.email, TRIM(u.tutor) AS grupo

                FROM users AS u

                WHERE u.tutor IS NOT NULL

                  AND TRIM(u.tutor) <> ''

                """

            )

            rows = list(cur.fetchall())

    rows = [

        {"grupo": str(r.get("grupo") or "").strip(), "name": r.get("name"), "email": r.get("email")}

        for r in rows

    ]

    rows.sort(

        key=lambda r: (

            normalize_for_sort(str(r.get("grupo") or "")),

            normalize_for_sort(str(r.get("name") or "")),

        )

    )

    return rows





def list_profesores_departamento_activos(dept: str) -> list[dict]:

    key = (dept or "").strip()

    if not key:

        return []

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT u.name, u.email

                FROM users AS u

                WHERE u.active = 1

                  AND LOWER(TRIM(COALESCE(u.status, 'activo'))) = 'activo'

                  AND LOWER(TRIM(u.departamento)) = LOWER(TRIM(%s))

                """,

                (key,),

            )

            rows = list(cur.fetchall())

    return _sort_prof_rows([{"name": r["name"], "email": r.get("email")} for r in rows])

