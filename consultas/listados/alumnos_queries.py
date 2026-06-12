"""Consultas para listados de alumnado."""



from __future__ import annotations



import re

import unicodedata

from datetime import date, datetime



from db.connection import get_db



# Columnas opcionales del listado (query param → etiqueta tabla, clave fila)

LISTADO_ALUMNOS_EXTRA_COLUMNS: tuple[tuple[str, str, str], ...] = (

    ("email", "Email", "email"),

    ("fecha_nacimiento", "F. nacimiento", "fecha_nacimiento_display"),

    ("cie", "CIE", "cie"),

    ("telefonos", "Teléfonos", "telefonos"),

)



LISTADO_ALUMNOS_EXTRA_PARAM_NAMES: frozenset[str] = frozenset(

    p[0] for p in LISTADO_ALUMNOS_EXTRA_COLUMNS

)



LISTADO_ALUMNOS_FILTROS: tuple[tuple[str, str], ...] = (

    ("todos", "Todos"),

    ("repetidores", "Repetidores"),

    ("difusion_imagen", "Difusión de imagen"),

    ("transporte", "Transporte"),

)



LISTADO_ALUMNOS_FILTRO_NAMES: frozenset[str] = frozenset(f[0] for f in LISTADO_ALUMNOS_FILTROS)



_FILTRO_WHERE_SQL: dict[str, str] = {

    "repetidores": "s.repetidor IS TRUE",

    "difusion_imagen": "s.difusion_imagen IS FALSE",

    "transporte": "s.transporte IS TRUE",

}



_FILTRO_TITLE_PART: dict[str, str] = {

    "repetidores": "Repetidores",

    "difusion_imagen": "Difusión de imagen: No",

    "transporte": "Transporte",

}



LISTADO_ALUMNOS_FILTRO_LEYENDAS: dict[str, str] = {

    "difusion_imagen": (

        "Solo alumnos con difusión de imagen en «No» (sin autorización de difusión de imagen)."

    ),

}



PARADA_LISTADO_SIN_PARADA = "Sin parada"



RESUMEN_ALUMNOS_FILTROS: tuple[tuple[str, str], ...] = (

    ("todos", "Todos"),

    ("repetidores", "Repetidores"),

    ("transporte", "Transporte"),

)



RESUMEN_ALUMNOS_FILTRO_NAMES: frozenset[str] = frozenset(f[0] for f in RESUMEN_ALUMNOS_FILTROS)



_RESUMEN_FETCH_WHERE_EXTRA: dict[str, str] = {

    "repetidores": " AND s.repetidor IS TRUE",

}





def normalize_alumnos_listado_filtro(raw: str | None) -> str:

    f = (raw or "todos").strip().lower()

    return f if f in LISTADO_ALUMNOS_FILTRO_NAMES else "todos"





def normalize_alumnos_resumen_filtro(raw: str | None) -> str:

    f = (raw or "todos").strip().lower()

    return f if f in RESUMEN_ALUMNOS_FILTRO_NAMES else "todos"



_LETTERS = ("A", "B", "C", "D")



_ETAPA_SEX_COLUMNS: tuple[tuple[str, str], ...] = (

    ("mujeres", "Mujeres"),

    ("varones", "Varones"),

)



_STAGE_COURSES: dict[str, list[tuple[int, str]]] = {

    "eso": [

        (1, "1ºESO"),

        (2, "2ºESO"),

        (3, "3ºESO"),

        (4, "4ºESO"),

    ],

    "bachillerato": [

        (1, "1ºBACH"),

        (2, "2ºBACH"),

    ],

    "fp": [

        (1, "1ºFPB"),

        (2, "2ºFPB"),

        (3, "1ºFPM"),

        (4, "2ºFPM"),

    ],

}





def _norm_text(value: str | None) -> str:

    text = (value or "").strip().lower()

    text = "".join(

        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"

    )

    return " ".join(text.split())





def _stage_of(*, grupo: str, curso: str | None) -> str | None:

    g = (grupo or "").strip()

    c = _norm_text(curso)



    if c:

        if "eso" in c and "bach" not in c and "fp" not in c:

            return "eso"

        if "bach" in c:

            return "bachillerato"

        if re.search(r"\bfp", c):

            return "fp"



    if re.match(r"^[1-4][A-Za-z]", g, re.IGNORECASE):

        return "eso"

    if re.match(r"^[56][A-Za-z]", g, re.IGNORECASE):

        return "bachillerato"

    if re.match(r"^fp[bm]\d", g, re.IGNORECASE):

        return "fp"

    return None





def _sex_column_key(sexo: str | None) -> str | None:

    s = (sexo or "").strip().upper()

    if s == "M":

        return "mujeres"

    if s == "V":

        return "varones"

    return None





def _empty_etapa_sex_counts() -> dict[str, int]:

    return {key: 0 for key, _ in _ETAPA_SEX_COLUMNS}





def _extract_letter(*, grupo: str, stage: str) -> str | None:

    g = (grupo or "").strip()



    if stage == "fp" and re.match(r"^fp[bm]\d", g, re.IGNORECASE):

        return "A"



    m = re.search(r"([A-D])\s*$", g, re.IGNORECASE)

    if not m:

        return None

    letter = m.group(1).upper()

    return letter if letter in _LETTERS else None





def _extract_course_num(*, grupo: str, curso: str | None, stage: str) -> int | None:

    allowed = {n for n, _ in _STAGE_COURSES[stage]}

    curso_s = (curso or "").strip()

    g = (grupo or "").strip()



    if curso_s:

        c = _norm_text(curso_s)

        if stage == "fp":

            m = re.search(r"(\d)\D*(fpb|fpm|fp\b)", c)

            if m:

                num = int(m.group(1))

                kind = m.group(2)

                if kind == "fpm":

                    mapped = {1: 3, 2: 4}.get(num)

                    if mapped in allowed:

                        return mapped

                elif num in (1, 2):

                    return num

        else:

            m = re.search(r"(\d)", curso_s)

            if m:

                num = int(m.group(1))

                if num in allowed:

                    return num



    if stage == "bachillerato":

        m = re.match(r"^([56])", g, re.IGNORECASE)

        if m:

            return {5: 1, 6: 2}.get(int(m.group(1)))



    if stage == "fp":

        m = re.match(r"^fp([bm])(\d)", g, re.IGNORECASE)

        if m:

            cycle, num = m.group(1).lower(), int(m.group(2))

            if cycle == "b" and num in (1, 2):

                return num

            if cycle == "m" and num in (1, 2):

                return {1: 3, 2: 4}[num]



    if stage == "eso":

        m = re.match(r"^(\d)", g)

        if m:

            num = int(m.group(1))

            if num in allowed:

                return num



    return None





def list_matricula_filter_cursos() -> list[str]:

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





def list_cursos_orden_tabla_grupos() -> list[str]:

    """Cursos en el orden de la tabla ``groups`` (por nombre de grupo, no alfabético por curso)."""

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT TRIM(curso) AS curso

                FROM groups

                WHERE curso IS NOT NULL AND btrim(curso) <> ''

                GROUP BY TRIM(curso), LOWER(TRIM(curso))

                ORDER BY MIN(name)

                """

            )

            return [str(r["curso"]).strip() for r in cur.fetchall() if r.get("curso")]





def _parada_listado_sql_filter(parada: str) -> tuple[str, list[str]]:

    if parada == PARADA_LISTADO_SIN_PARADA:

        return "(s.parada IS NULL OR btrim(s.parada) = '')", []

    return "LOWER(TRIM(s.parada)) = LOWER(TRIM(%s))", [parada]





def list_matricula_filter_paradas(

    *,

    curso: str | None = None,

    grupo: str | None = None,

) -> list[str]:

    """Paradas de alumnos con transporte, opcionalmente acotadas por curso o grupo."""

    curso = (curso or "").strip() or None

    grupo = (grupo or "").strip() or None

    clauses = [

        "s.transporte IS TRUE",

        "s.grupo IS NOT NULL",

        "btrim(s.grupo) <> ''",

    ]

    params: list[str] = []

    if curso:

        clauses.append("LOWER(TRIM(g.curso)) = LOWER(TRIM(%s))")

        params.append(curso)

    if grupo:

        clauses.append("LOWER(TRIM(s.grupo)) = LOWER(TRIM(%s))")

        params.append(grupo)



    where_sql = " AND ".join(clauses)

    sin = PARADA_LISTADO_SIN_PARADA

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                f"""

                SELECT COALESCE(NULLIF(btrim(s.parada), ''), %s) AS parada

                FROM students s

                LEFT JOIN groups g ON LOWER(TRIM(g.name)) = LOWER(TRIM(s.grupo))

                WHERE {where_sql}

                """,

                params + [sin],

            )

            paradas = {str(r["parada"]).strip() for r in cur.fetchall() if r.get("parada")}

    return sorted(paradas, key=_norm_text)





def list_matricula_filter_grupos(*, curso: str | None = None) -> list[str]:

    curso = (curso or "").strip() or None

    with get_db() as conn:

        with conn.cursor() as cur:

            if curso:

                cur.execute(

                    """

                    SELECT name

                    FROM groups

                    WHERE curso IS NOT NULL

                      AND btrim(curso) <> ''

                      AND LOWER(TRIM(curso)) = LOWER(TRIM(%s))

                    ORDER BY name

                    """,

                    (curso,),

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





def _resumen_fetch_extra(filtro: str) -> str:

    return _RESUMEN_FETCH_WHERE_EXTRA.get(normalize_alumnos_resumen_filtro(filtro), "")





def _fetch_group_counts(*, filtro: str = "todos") -> list[dict]:

    extra = _resumen_fetch_extra(filtro)

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                f"""

                SELECT s.grupo, g.curso, COUNT(*)::int AS n

                FROM students s

                LEFT JOIN groups g ON LOWER(TRIM(g.name)) = LOWER(TRIM(s.grupo))

                WHERE s.grupo IS NOT NULL AND btrim(s.grupo) <> ''{extra}

                GROUP BY s.grupo, g.curso

                """

            )

            return cur.fetchall()





def _fetch_group_sexo_counts(*, filtro: str = "todos") -> list[dict]:

    extra = _resumen_fetch_extra(filtro)

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                f"""

                SELECT s.grupo, g.curso, UPPER(TRIM(s.sexo)) AS sexo, COUNT(*)::int AS n

                FROM students s

                LEFT JOIN groups g ON LOWER(TRIM(g.name)) = LOWER(TRIM(s.grupo))

                WHERE s.grupo IS NOT NULL AND btrim(s.grupo) <> ''

                  AND s.sexo IS NOT NULL

                  AND UPPER(TRIM(s.sexo)) IN ('M', 'V'){extra}

                GROUP BY s.grupo, g.curso, UPPER(TRIM(s.sexo))

                """

            )

            return cur.fetchall()





def _fetch_transporte_parada_curso_counts() -> list[dict]:

    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                """

                SELECT

                    COALESCE(NULLIF(btrim(s.parada), ''), 'Sin parada') AS parada,

                    TRIM(g.curso) AS curso,

                    COUNT(*)::int AS n

                FROM students s

                LEFT JOIN groups g ON LOWER(TRIM(g.name)) = LOWER(TRIM(s.grupo))

                WHERE s.transporte IS TRUE

                  AND s.grupo IS NOT NULL AND btrim(s.grupo) <> ''

                  AND g.curso IS NOT NULL AND btrim(g.curso) <> ''

                GROUP BY 1, 2

                """

            )

            return cur.fetchall()





_ETAPA_LABELS = {

    "eso": "ESO",

    "bachillerato": "BACH",

    "fp": "FP",

}





def _build_etapas_resumen(sex_grids: dict[str, dict[str, int]]) -> dict:

    """Totales por etapa (ESO, BACH, FP) con Mujeres, Varones y Totales."""

    rows: list[dict] = []

    column_totals = _empty_etapa_sex_counts()

    grand_total = 0



    for stage in _ETAPA_LABELS:

        counts = {key: sex_grids[stage][key] for key, _ in _ETAPA_SEX_COLUMNS}

        row_total = sum(counts.values())

        rows.append({"label": _ETAPA_LABELS[stage], "counts": counts, "total": row_total})

        for key, _ in _ETAPA_SEX_COLUMNS:

            column_totals[key] += counts[key]

        grand_total += row_total



    return {

        "columns": [{"key": k, "label": lbl} for k, lbl in _ETAPA_SEX_COLUMNS],

        "rows": rows,

        "column_totals": column_totals,

        "grand_total": grand_total,

    }





def _build_stage_resumen(stage: str, grid: dict[int, dict[str, int]]) -> dict:

    table_rows: list[dict] = []

    grand_total = 0



    for course_num, label in _STAGE_COURSES[stage]:

        counts = {letter: grid[course_num][letter] for letter in _LETTERS}

        row_total = sum(counts.values())

        table_rows.append({"label": label, "counts": counts, "total": row_total})

        grand_total += row_total



    return {

        "letters": list(_LETTERS),

        "rows": table_rows,

        "grand_total": grand_total,

    }





def build_transporte_parada_resumen() -> dict:

    """Paradas (filas) × cursos (columnas); totales en última columna y fila."""

    raw = _fetch_transporte_parada_curso_counts()

    cursos: list[str] = list_cursos_orden_tabla_grupos()

    curso_set = set(cursos)

    for row in raw:

        c = str(row.get("curso") or "").strip()

        if c and c not in curso_set:

            cursos.append(c)

            curso_set.add(c)



    grid: dict[str, dict[str, int]] = {}

    for row in raw:

        parada = str(row.get("parada") or "Sin parada").strip()

        curso = str(row.get("curso") or "").strip()

        if not curso:

            continue

        grid.setdefault(parada, {c: 0 for c in cursos})

        grid[parada][curso] += int(row.get("n") or 0)



    paradas = sorted(grid.keys(), key=_norm_text)

    column_totals = {c: 0 for c in cursos}

    grand_total = 0

    table_rows: list[dict] = []



    for parada in paradas:

        counts = {c: grid[parada].get(c, 0) for c in cursos}

        row_total = sum(counts.values())

        table_rows.append({"label": parada, "counts": counts, "total": row_total})

        for c in cursos:

            column_totals[c] += counts[c]

        grand_total += row_total



    return {

        "columns": [{"key": c, "label": c} for c in cursos],

        "rows": table_rows,

        "column_totals": column_totals,

        "grand_total": grand_total,

    }





def build_matricula_resumenes(*, filtro: str = "todos") -> dict[str, dict]:

    """Resúmenes ESO/BACH/FP por grupos A–D; tabla superior por sexo."""

    filtro = normalize_alumnos_resumen_filtro(filtro)

    letter_grids: dict[str, dict[int, dict[str, int]]] = {

        stage: {n: {letter: 0 for letter in _LETTERS} for n, _ in courses}

        for stage, courses in _STAGE_COURSES.items()

    }

    sex_grids: dict[str, dict[str, int]] = {

        stage: _empty_etapa_sex_counts() for stage in _ETAPA_LABELS

    }



    for row in _fetch_group_counts(filtro=filtro):

        grupo = str(row.get("grupo") or "")

        curso = str(row.get("curso") or "") if row.get("curso") is not None else None

        stage = _stage_of(grupo=grupo, curso=curso)

        if stage is None:

            continue

        course_num = _extract_course_num(grupo=grupo, curso=curso, stage=stage)

        letter = _extract_letter(grupo=grupo, stage=stage)

        if course_num is None or letter is None:

            continue

        letter_grids[stage][course_num][letter] += int(row.get("n") or 0)



    for row in _fetch_group_sexo_counts(filtro=filtro):

        grupo = str(row.get("grupo") or "")

        curso = str(row.get("curso") or "") if row.get("curso") is not None else None

        stage = _stage_of(grupo=grupo, curso=curso)

        sex_key = _sex_column_key(str(row.get("sexo") or ""))

        if stage is None or sex_key is None:

            continue

        sex_grids[stage][sex_key] += int(row.get("n") or 0)



    stages = {

        stage: _build_stage_resumen(stage, letter_grids[stage]) for stage in _STAGE_COURSES

    }

    stages["etapas"] = _build_etapas_resumen(sex_grids)

    return stages





def _fecha_display(value: object) -> str:

    if isinstance(value, datetime):

        return value.date().strftime("%d/%m/%Y")

    if isinstance(value, date):

        return value.strftime("%d/%m/%Y")

    if value:

        return str(value)[:10]

    return ""





def _telefonos_display(t1: object, t2: object) -> str:

    parts = [str(x).strip() for x in (t1, t2) if x is not None and str(x).strip()]

    return " / ".join(parts)





def list_alumnos_filtrados(

    *,

    curso: str | None = None,

    grupo: str | None = None,

    parada: str | None = None,

    filtro: str = "todos",

) -> list[dict]:

    """Listado de alumnos filtrado por curso, grupo y/o parada (orden alfabético por nombre)."""

    curso = (curso or "").strip() or None

    grupo = (grupo or "").strip() or None

    parada = (parada or "").strip() or None

    filtro = normalize_alumnos_listado_filtro(filtro)

    if not curso and not grupo and not parada:

        return []



    clauses = ["s.grupo IS NOT NULL", "btrim(s.grupo) <> ''"]

    params: list[str] = []



    if grupo:

        clauses.append("LOWER(TRIM(s.grupo)) = LOWER(TRIM(%s))")

        params.append(grupo)

    if curso:

        clauses.append("LOWER(TRIM(g.curso)) = LOWER(TRIM(%s))")

        params.append(curso)

    if parada:

        parada_sql, parada_params = _parada_listado_sql_filter(parada)

        clauses.append(parada_sql)

        params.extend(parada_params)

    if filtro in _FILTRO_WHERE_SQL:

        clauses.append(_FILTRO_WHERE_SQL[filtro])



    where_sql = " AND ".join(clauses)

    order_sql = "LOWER(TRIM(s.alumno)), LOWER(TRIM(COALESCE(s.grupo, '')))"



    with get_db() as conn:

        with conn.cursor() as cur:

            cur.execute(

                f"""

                SELECT s.alumno, s.email_student, s.grupo,

                       s.fecha_nacimiento, s.cie,

                       s.telefono1, s.telefono2, s.parada

                FROM students s

                LEFT JOIN groups g ON LOWER(TRIM(g.name)) = LOWER(TRIM(s.grupo))

                WHERE {where_sql}

                ORDER BY {order_sql}

                """,

                params,

            )

            rows = cur.fetchall()



    out = [

        {

            "alumno": str(r.get("alumno") or ""),

            "email": (str(r.get("email_student") or "").strip() or None),

            "grupo": str(r.get("grupo") or "").strip(),

            "fecha_nacimiento_display": _fecha_display(r.get("fecha_nacimiento")),

            "cie": (str(r.get("cie") or "").strip() or None),

            "telefonos": _telefonos_display(r.get("telefono1"), r.get("telefono2")),

            "parada": (str(r.get("parada") or "").strip() or None),

        }

        for r in rows

    ]

    out.sort(key=lambda r: (_norm_text(r["alumno"]), _norm_text(r.get("grupo") or "")))

    return out





def build_matricula_resumen_eso() -> dict:

    """Compatibilidad: solo resumen ESO."""

    return build_matricula_resumenes()["eso"]





def alumnos_listado_bundle(

    *,

    curso: str | None = None,

    grupo: str | None = None,

    parada: str | None = None,

    extra_cols: frozenset[str] | None = None,

    filtro: str = "todos",

) -> tuple[list[tuple[str, str]], list[dict], str, bool]:

    """Columnas (etiqueta, clave), filas, título exportación y si se puede exportar."""

    curso = (curso or "").strip() or None

    grupo = (grupo or "").strip() or None

    parada = (parada or "").strip() or None

    filtro = normalize_alumnos_listado_filtro(filtro)

    active_extra = extra_cols or frozenset()

    rows = list_alumnos_filtrados(

        curso=curso, grupo=grupo, parada=parada, filtro=filtro

    )

    can_export = bool(curso or grupo or parada)



    parts: list[str] = []

    if curso:

        parts.append(curso)

    if grupo:

        parts.append(f"Grupo {grupo}")

    if parada:

        parts.append(f"Parada {parada}")

    if filtro in _FILTRO_TITLE_PART:

        parts.append(_FILTRO_TITLE_PART[filtro])

    title = " — ".join(parts) if parts else "Alumnos"



    show_grupo_col = (curso and not grupo) or (parada and not grupo)

    if show_grupo_col:

        columns: list[tuple[str, str]] = [

            ("Alumnos", "alumno"),

            ("Grupo", "grupo"),

        ]

    else:

        columns = [("Alumno", "alumno")]



    for param, label, key in LISTADO_ALUMNOS_EXTRA_COLUMNS:

        if param in active_extra:

            columns.append((label, key))



    if (

        filtro == "transporte"

        and not parada

        and not any(k == "parada" for _, k in columns)

    ):

        columns.append(("Parada", "parada"))



    return (columns, rows, title, can_export)

