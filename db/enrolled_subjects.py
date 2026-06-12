"""Asignaturas matriculadas (importación Excel → tabla ``enrolled_subjects``)."""

from __future__ import annotations

import unicodedata
from typing import Any

from db.connection import get_db

# Cabeceras oficiales del Excel (exportación)
EXCEL_HEADERS: tuple[str, ...] = (
    "ALUMNO",
    "MATERIA (abrev.)",
    "MATERIA",
    "BILINGÜE",
    "ESTUDIO",
    "CURSO",
    "NOMBRE GRUPO",
    "CARACTERISTICAS",
    "DEPARTAMENTO",
)

FIELD_NAMES: tuple[str, ...] = (
    "alumno",
    "materia_abrev",
    "materia",
    "bilingue",
    "estudio",
    "curso",
    "nombre_grupo",
    "caracteristicas",
    "departamento",
)

FIELD_TO_EXCEL: dict[str, str] = dict(zip(FIELD_NAMES, EXCEL_HEADERS))

# Columnas visibles en /listados/asignaturas (campo BD, etiqueta)
LISTADO_DISPLAY_COLUMNS: tuple[tuple[str, str], ...] = (
    ("alumno", "Alumno"),
    ("nombre_grupo", "Grupo"),
    ("materia_abrev", "Materia (abrev.)"),
)

# Valor en columna ``caracteristicas`` para asignaturas pendientes (vista Pendientes).
CARACTERISTICA_MATERIA_PENDIENTE = "PT-Materia pendiente"

# Excel: ``curso`` = curso del alumno. El curso de la asignatura está en
# ``enrolled_subject_catalog`` (importación aparte en el portal).


def _norm_header(value: object) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    return " ".join(text.split())


def _norm_curso_key(value: str | None) -> str:
    """Clave de curso sin espacios ni tildes (1º ESO = 1ºESO)."""
    text = (value or "").strip().lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    text = text.replace("º", "o").replace("°", "o")
    return "".join(text.split())


def _sql_curso_key(column: str) -> str:
    return (
        f"LOWER(REGEXP_REPLACE("
        f"REGEXP_REPLACE(TRIM({column}), '\\s+', '', 'g'), "
        f"'[º°]', 'o', 'g'))"
    )


def _header_to_field(norm: str) -> str | None:
    """
    Solo las 9 columnas oficiales; cualquier otra cabecera del Excel se ignora.
    ``materia_abrev`` debe resolverse antes que ``materia``.
    """
    if not norm:
        return None
    if norm in {
        "alumno",
        "alumnos",
        "nombre alumno",
        "nombre del alumno",
        "nombre y apellidos",
        "apellidos y nombre",
        "alumno/a",
    }:
        return "alumno"
    if "materia" in norm and "abrev" in norm:
        return "materia_abrev"
    if norm == "materia":
        return "materia"
    if norm == "bilingue" or norm.startswith("bilingue "):
        return "bilingue"
    if norm == "estudio":
        return "estudio"
    if norm == "curso":
        return "curso"
    if norm in {
        "nombre grupo",
        "nombre de grupo",
        "cod. grupo",
        "cod grupo",
        "codigo grupo",
        "codigo de grupo",
    } or (norm.startswith("cod") and "grupo" in norm):
        return "nombre_grupo"
    if norm in {"caracteristicas", "caracteristica"}:
        return "caracteristicas"
    if norm == "departamento":
        return "departamento"
    return None


def map_headers_to_fields(headers: list[str]) -> dict[int, str]:
    """Índice de columna Excel → campo BD (solo columnas conocidas; una por campo)."""
    idx_to_field: dict[int, str] = {}
    used_fields: set[str] = set()
    for pos, raw in enumerate(headers):
        field = _header_to_field(_norm_header(raw))
        if field is None or field in used_fields:
            continue
        idx_to_field[pos] = field
        used_fields.add(field)
    return idx_to_field


def find_header_row(ws, *, max_scan: int = 30) -> tuple[int, list[str]] | None:
    """Localiza la fila de cabeceras (la que contiene ALUMNO)."""
    for row_idx, row in enumerate(
        ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), start=1
    ):
        if not row:
            continue
        headers = [str(c).strip() if c is not None else "" for c in row]
        mapped = map_headers_to_fields(headers)
        if "alumno" in mapped.values():
            return row_idx, headers
    return None


def parse_worksheet_rows(ws) -> tuple[dict[int, str], list[dict[str, str | None]]]:
    """Lee filas de datos usando solo las columnas oficiales."""
    found = find_header_row(ws)
    if not found:
        return {}, []

    header_row_idx, headers = found
    idx_to_field = map_headers_to_fields(headers)
    if "alumno" not in idx_to_field.values():
        return idx_to_field, []

    parsed: list[dict[str, str | None]] = []
    for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
        if not row or all(
            c is None or (isinstance(c, str) and not c.strip()) for c in row
        ):
            continue
        record = row_from_excel_values(values=row, idx_to_field=idx_to_field)
        if not (record.get("alumno") or "").strip():
            continue
        parsed.append(record)
    return idx_to_field, parsed


def parse_workbook_rows(wb) -> tuple[dict[int, str], list[dict[str, str | None]]]:
    """Busca la hoja con cabecera ALUMNO (no solo la hoja activa)."""
    best_idx: dict[int, str] = {}
    best_rows: list[dict[str, str | None]] = []
    for sheet_name in wb.sheetnames:
        idx_to_field, rows = parse_worksheet_rows(wb[sheet_name])
        if "alumno" not in idx_to_field.values():
            continue
        if len(rows) > len(best_rows):
            best_idx = idx_to_field
            best_rows = rows
    return best_idx, best_rows


def row_from_excel_values(
    *,
    values: tuple[object, ...],
    idx_to_field: dict[int, str],
) -> dict[str, str | None]:
    record = {name: None for name in FIELD_NAMES}
    for pos, field in idx_to_field.items():
        raw = values[pos] if pos < len(values) else None
        if raw is None:
            record[field] = None
        elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
            record[field] = str(raw).strip() or None
        else:
            s = str(raw).strip()
            record[field] = s if s else None
    return record


_enrolled_schema_ready = False


def ensure_enrolled_subjects_schema() -> None:
    global _enrolled_schema_ready
    if _enrolled_schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS enrolled_subjects_imports (
                    id SERIAL PRIMARY KEY,
                    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    imported_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    filename TEXT,
                    row_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS enrolled_subjects (
                    id SERIAL PRIMARY KEY,
                    import_id INTEGER NOT NULL
                        REFERENCES enrolled_subjects_imports(id) ON DELETE CASCADE,
                    row_number INTEGER NOT NULL,
                    alumno TEXT NOT NULL,
                    materia_abrev TEXT,
                    materia TEXT,
                    bilingue TEXT,
                    estudio TEXT,
                    curso TEXT,
                    nombre_grupo TEXT,
                    caracteristicas TEXT,
                    departamento TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_enrolled_subjects_import
                ON enrolled_subjects (import_id, row_number)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_enrolled_subjects_alumno
                ON enrolled_subjects (LOWER(TRIM(alumno)))
                """
            )
            cur.execute("DROP TABLE IF EXISTS enrolled_subjects_rows")
            # Quitar columna headers si existía en imports antiguos
            cur.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'enrolled_subjects_imports'
                          AND column_name = 'headers'
                    ) THEN
                        ALTER TABLE enrolled_subjects_imports DROP COLUMN headers;
                    END IF;
                END $$
                """
            )
            cur.execute(
                """
                ALTER TABLE enrolled_subjects
                ADD COLUMN IF NOT EXISTS curso_asignatura SMALLINT
                """
            )
    _enrolled_schema_ready = True


def replace_import(
    *,
    imported_by: int | None,
    filename: str | None,
    rows: list[dict[str, str | None]],
) -> int:
    """Sustituye la importación anterior por la nueva."""
    ensure_enrolled_subjects_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM enrolled_subjects")
            cur.execute("DELETE FROM enrolled_subjects_imports")
            cur.execute(
                """
                INSERT INTO enrolled_subjects_imports (
                    imported_by, filename, row_count
                )
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (
                    imported_by,
                    (filename or "").strip() or None,
                    len(rows),
                ),
            )
            import_id = int(cur.fetchone()["id"])
            for row_num, row in enumerate(rows, start=1):
                cur.execute(
                    """
                    INSERT INTO enrolled_subjects (
                        import_id, row_number,
                        alumno, materia_abrev, materia, bilingue,
                        estudio, curso, nombre_grupo, caracteristicas, departamento
                    )
                    VALUES (
                        %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s
                    )
                    """,
                    (
                        import_id,
                        row_num,
                        row.get("alumno") or "",
                        row.get("materia_abrev"),
                        row.get("materia"),
                        row.get("bilingue"),
                        row.get("estudio"),
                        row.get("curso"),
                        row.get("nombre_grupo"),
                        row.get("caracteristicas"),
                        row.get("departamento"),
                    ),
                )
            return import_id


def get_latest_import() -> dict | None:
    ensure_enrolled_subjects_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT i.id, i.imported_at, i.filename, i.row_count,
                       u.name AS imported_by_name
                FROM enrolled_subjects_imports i
                LEFT JOIN users u ON u.id = i.imported_by
                ORDER BY i.id DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
    if not row:
        return None
    return {
        "id": int(row["id"]),
        "imported_at": row.get("imported_at"),
        "filename": row.get("filename"),
        "row_count": int(row.get("row_count") or 0),
        "imported_by_name": row.get("imported_by_name"),
    }


def _row_to_dict(r: dict) -> dict[str, Any]:
    return {
        "row_number": int(r["row_number"]),
        "alumno": r.get("alumno") or "",
        "materia_abrev": r.get("materia_abrev"),
        "materia": r.get("materia"),
        "bilingue": r.get("bilingue"),
        "estudio": r.get("estudio"),
        "curso": r.get("curso"),
        "nombre_grupo": r.get("nombre_grupo"),
        "caracteristicas": r.get("caracteristicas"),
        "departamento": r.get("departamento"),
    }


_ROW_SELECT = """
    SELECT row_number, alumno, materia_abrev, materia, bilingue,
           estudio, curso, nombre_grupo, caracteristicas, departamento
    FROM enrolled_subjects
"""

_LISTADO_ROW_SELECT = """
    SELECT row_number, alumno, materia_abrev, materia, bilingue,
           estudio,
           COALESCE(
             (
               SELECT g.curso
               FROM students s
               INNER JOIN groups g ON LOWER(TRIM(g.name)) = LOWER(TRIM(s.grupo))
               WHERE LOWER(TRIM(s.alumno)) = LOWER(TRIM(enrolled_subjects.alumno))
               ORDER BY s.grupo
               LIMIT 1
             ),
             (
               SELECT g.curso
               FROM groups g
               WHERE LOWER(TRIM(g.name)) = LOWER(TRIM(enrolled_subjects.nombre_grupo))
               LIMIT 1
             )
           ) AS curso,
           nombre_grupo, caracteristicas, departamento
    FROM enrolled_subjects
"""


def _latest_import_id() -> int | None:
    latest = get_latest_import()
    return int(latest["id"]) if latest else None


def _student_scope_clause(
    *,
    curso_grupos: str | None = None,
    grupo: str | None = None,
    skip: frozenset[str] | None = None,
) -> tuple[str | None, list[Any]]:
    """
    Acota filas al curso/grupo del alumno (``students`` + ``groups``) o al
    ``nombre_grupo`` importado (COD. GRUPO) si coincide con ``groups.name``.
    """
    skip = skip or frozenset()
    curso_v = (curso_grupos or "").strip()
    grupo_v = (grupo or "").strip()
    apply_curso = bool(curso_v) and "curso_grupos" not in skip
    apply_grupo = bool(grupo_v) and "grupo" not in skip
    if not apply_curso and not apply_grupo:
        return None, []

    curso_key = _norm_curso_key(curso_v) if apply_curso else None
    g_curso = _sql_curso_key("g.curso")
    params: list[Any] = []

    via_student = [
        "EXISTS (",
        "  SELECT 1",
        "  FROM students s",
        "  INNER JOIN groups g ON LOWER(TRIM(g.name)) = LOWER(TRIM(s.grupo))",
        "  WHERE LOWER(TRIM(s.alumno)) = LOWER(TRIM(enrolled_subjects.alumno))",
    ]
    if apply_curso:
        via_student.append(f"    AND {g_curso} = %s")
        params.append(curso_key)
    if apply_grupo:
        via_student.append("    AND LOWER(TRIM(s.grupo)) = LOWER(TRIM(%s))")
        params.append(grupo_v)
    via_student.append(")")

    via_cod_grupo = [
        "EXISTS (",
        "  SELECT 1",
        "  FROM groups g",
        "  WHERE LOWER(TRIM(g.name)) = LOWER(TRIM(enrolled_subjects.nombre_grupo))",
    ]
    if apply_curso:
        via_cod_grupo.append(f"    AND {g_curso} = %s")
        params.append(curso_key)
    if apply_grupo:
        via_cod_grupo.append("    AND LOWER(TRIM(g.name)) = LOWER(TRIM(%s))")
        params.append(grupo_v)
    via_cod_grupo.append(")")

    sql = "(" + "\n  OR ".join(["\n".join(via_student), "\n".join(via_cod_grupo)]) + ")"
    return sql, params


def _curso_asignatura_clause(
    curso_asignatura: int | None,
    *,
    skip: frozenset[str] | None = None,
) -> tuple[str | None, list[Any]]:
    """Filtra por curso de la asignatura (``enrolled_subject_catalog.curso_asignatura``)."""
    skip = skip or frozenset()
    if curso_asignatura is None or "curso_asignatura" in skip:
        return None, []
    sql = """
        EXISTS (
          SELECT 1
          FROM enrolled_subject_catalog c
          WHERE TRIM(c.materia_abrev) = TRIM(enrolled_subjects.materia_abrev)
            AND c.curso_asignatura = %s
        )
    """
    return sql, [curso_asignatura]


def _filter_where(
    import_id: int,
    *,
    curso_grupos: str | None = None,
    curso_asignatura: int | None = None,
    grupo: str | None = None,
    alumno: str | None = None,
    materia: str | None = None,
    solo_pendientes: bool = False,
    skip: frozenset[str] | None = None,
) -> tuple[str, list[Any]]:
    """
    ``curso_grupos``: curso del alumno en ``groups`` (p. ej. 3º ESO).
    ``curso_asignatura``: curso de la asignatura en el catálogo (1, 2, 3…).
    """
    skip = skip or frozenset()
    clauses = ["import_id = %s"]
    params: list[Any] = [import_id]

    scope_sql, scope_params = _student_scope_clause(
        curso_grupos=curso_grupos,
        grupo=grupo,
        skip=skip,
    )
    if scope_sql:
        clauses.append(scope_sql)
        params.extend(scope_params)

    ca_sql, ca_params = _curso_asignatura_clause(curso_asignatura, skip=skip)
    if ca_sql:
        clauses.append(ca_sql)
        params.extend(ca_params)

    alumno_v = (alumno or "").strip()
    if alumno_v and "alumno" not in skip:
        clauses.append("LOWER(TRIM(alumno)) = LOWER(TRIM(%s))")
        params.append(alumno_v)

    materia_v = (materia or "").strip()
    if materia_v and "materia" not in skip:
        clauses.append("materia = %s")
        params.append(materia_v)

    if solo_pendientes:
        clauses.append("TRIM(caracteristicas) = %s")
        params.append(CARACTERISTICA_MATERIA_PENDIENTE)

    return " AND ".join(clauses), params


def _distinct_values(
    column: str,
    *,
    curso_grupos: str | None = None,
    curso_asignatura: int | None = None,
    grupo: str | None = None,
    alumno: str | None = None,
    materia: str | None = None,
    solo_pendientes: bool = False,
    skip_key: str,
) -> list[str]:
    import_id = _latest_import_id()
    if not import_id:
        return []
    where, params = _filter_where(
        import_id,
        curso_grupos=curso_grupos,
        curso_asignatura=curso_asignatura,
        grupo=grupo,
        alumno=alumno,
        materia=materia,
        solo_pendientes=solo_pendientes,
        skip=frozenset({skip_key}),
    )
    ensure_enrolled_subjects_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT {column} AS value
                FROM enrolled_subjects
                WHERE {where}
                  AND {column} IS NOT NULL
                  AND TRIM({column}) <> ''
                ORDER BY value
                """,
                params,
            )
            return [str(r["value"]).strip() for r in cur.fetchall()]


def list_enrolled_filter_grupos(
    *,
    curso_grupos: str | None = None,
    curso_asignatura: int | None = None,
    solo_pendientes: bool = False,
) -> list[str]:
    return _distinct_values(
        "nombre_grupo",
        curso_grupos=curso_grupos,
        curso_asignatura=curso_asignatura,
        solo_pendientes=solo_pendientes,
        skip_key="grupo",
    )


def list_enrolled_filter_alumnos(
    *,
    curso_grupos: str | None = None,
    curso_asignatura: int | None = None,
    grupo: str | None = None,
    solo_pendientes: bool = False,
) -> list[str]:
    return _distinct_values(
        "alumno",
        curso_grupos=curso_grupos,
        curso_asignatura=curso_asignatura,
        grupo=grupo,
        solo_pendientes=solo_pendientes,
        skip_key="alumno",
    )


def list_enrolled_filter_materias(
    *,
    curso_grupos: str | None = None,
    curso_asignatura: int | None = None,
    grupo: str | None = None,
    alumno: str | None = None,
    solo_pendientes: bool = False,
) -> list[str]:
    return _distinct_values(
        "materia",
        curso_grupos=curso_grupos,
        curso_asignatura=curso_asignatura,
        grupo=grupo,
        alumno=alumno,
        solo_pendientes=solo_pendientes,
        skip_key="materia",
    )


def list_distinct_curso_asignatura_options(*, solo_pendientes: bool = False) -> list[dict[str, str]]:
    """Opciones de filtro curso = curso de la asignatura (valor numérico, etiqueta Nº)."""
    import_id = _latest_import_id()
    if not import_id:
        return []
    ensure_enrolled_subjects_schema()
    from db.enrolled_subject_catalog import ensure_subject_catalog_schema

    ensure_subject_catalog_schema()
    extra = ""
    params: list[Any] = [import_id]
    if solo_pendientes:
        extra = " AND TRIM(es.caracteristicas) = %s"
        params.append(CARACTERISTICA_MATERIA_PENDIENTE)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT c.curso_asignatura AS n
                FROM enrolled_subject_catalog c
                INNER JOIN enrolled_subjects es
                  ON TRIM(es.materia_abrev) = TRIM(c.materia_abrev)
                WHERE es.import_id = %s
                  AND c.curso_asignatura IS NOT NULL
                  {extra}
                ORDER BY c.curso_asignatura
                """,
                params,
            )
            rows = cur.fetchall()
    return [
        {"value": str(int(r["n"])), "label": f"{int(r['n'])}º"}
        for r in rows
        if r.get("n") is not None
    ]


def list_enrolled_subject_rows(
    *,
    curso_grupos: str | None = None,
    curso_asignatura: int | None = None,
    grupo: str | None = None,
    alumno: str | None = None,
    materia: str | None = None,
    solo_pendientes: bool = False,
) -> list[dict[str, Any]]:
    import_id = _latest_import_id()
    if not import_id:
        return []
    where, params = _filter_where(
        import_id,
        curso_grupos=curso_grupos,
        curso_asignatura=curso_asignatura,
        grupo=grupo,
        alumno=alumno,
        materia=materia,
        solo_pendientes=solo_pendientes,
    )
    ensure_enrolled_subjects_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                {_LISTADO_ROW_SELECT}
                WHERE {where}
                ORDER BY
                  LOWER(TRIM(COALESCE(nombre_grupo, ''))),
                  LOWER(TRIM(alumno)),
                  LOWER(TRIM(COALESCE(materia_abrev, materia, '')))
                """,
                params,
            )
            return [_row_to_dict(r) for r in cur.fetchall()]


def list_preview_rows(*, limit: int = 50) -> list[dict[str, Any]]:
    ensure_enrolled_subjects_schema()
    latest = get_latest_import()
    if not latest:
        return []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT row_number, alumno, materia_abrev, materia, bilingue,
                       estudio, curso, nombre_grupo, caracteristicas, departamento
                FROM enrolled_subjects
                WHERE import_id = %s
                ORDER BY row_number
                LIMIT %s
                """,
                (latest["id"], limit),
            )
            return [_row_to_dict(r) for r in cur.fetchall()]


def list_all_rows() -> list[dict[str, Any]]:
    latest = get_latest_import()
    if not latest:
        return []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT row_number, alumno, materia_abrev, materia, bilingue,
                       estudio, curso, nombre_grupo, caracteristicas, departamento
                FROM enrolled_subjects
                WHERE import_id = %s
                ORDER BY row_number
                """,
                (latest["id"],),
            )
            return [_row_to_dict(r) for r in cur.fetchall()]
