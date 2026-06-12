"""Resúmenes de asignaturas pendientes (matrices por etapa)."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable

from db.enrolled_subjects import CARACTERISTICA_MATERIA_PENDIENTE, get_latest_import
from db.enrolled_subject_catalog import (
    bach_pendiente_subject_modalidad,
    catalog_row_belongs_to_stage,
    ensure_subject_catalog_schema,
    fetch_bach_pendientes_matrix_catalog,
    get_catalog_meta,
    merge_bach_pendientes_matrix_resumen,
    resolve_catalog_stage,
)
from db.connection import get_db
from utils.text import normalize_for_sort

PENDIENTES_RESUMEN_TABLES: tuple[tuple[str, str], ...] = (
    ("eso", "ESO"),
    ("bach", "BACHILLERATO"),
    ("fp", "FP"),
)

PENDIENTES_ESO_ALUMNO_CURSOS: tuple[int, ...] = (2, 3, 4)
PENDIENTES_BACH_ALUMNO_CURSO = 2
PENDIENTES_BACH_MODALIDADES: tuple[tuple[str, str], ...] = (
    ("bhs", "BHS"),
    ("bct", "BCT"),
)
PENDIENTES_FP_ALUMNO_CURSO = 2
_FP_ETAPAS: tuple[str, ...] = ("fpb", "fpm")

_ALUMNO_CURSO_RESUELTO_SQL = """
COALESCE(
  (
    SELECT g.curso
    FROM students s
    INNER JOIN groups g ON LOWER(TRIM(g.name)) = LOWER(TRIM(s.grupo))
    WHERE LOWER(TRIM(s.alumno)) = LOWER(TRIM(es.alumno))
    ORDER BY s.grupo
    LIMIT 1
  ),
  (
    SELECT g.curso
    FROM groups g
    WHERE LOWER(TRIM(g.name)) = LOWER(TRIM(es.nombre_grupo))
    LIMIT 1
  ),
  es.curso
)
"""

_ALUMNO_GRUPO_RESUELTO_SQL = """
COALESCE(
  (
    SELECT s.grupo
    FROM students s
    WHERE LOWER(TRIM(s.alumno)) = LOWER(TRIM(es.alumno))
    ORDER BY s.grupo
    LIMIT 1
  ),
  es.nombre_grupo
)
"""


def _latest_import_id() -> int | None:
    latest = get_latest_import()
    return int(latest["id"]) if latest else None


def _materia_label(*, materia: str | None, materia_abrev: str | None, curso: int) -> str:
    nombre = (materia or materia_abrev or "").strip()
    return f"{nombre} ({curso}º)"


def _matrix_columns(keys: tuple[int, ...]) -> list[dict[str, Any]]:
    return [{"key": n, "label": f"{n}º"} for n in keys]


def _bach_matrix_columns() -> list[dict[str, Any]]:
    return [{"key": key, "label": label} for key, label in PENDIENTES_BACH_MODALIDADES]


def _empty_matrix_resumen(*, columns: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "layout": "matrix",
        "columns": columns,
        "column_totals": {col["key"]: 0 for col in columns},
        "grand_total": 0,
        "rows": [],
    }


def _resolve_row_etapa(row: dict[str, Any]) -> str | None:
    return resolve_catalog_stage(
        etapa=row.get("etapa") or row.get("catalog_etapa"),
        estudio=row.get("estudio") or row.get("catalog_estudio"),
        materia_abrev=row.get("materia_abrev"),
        materia=row.get("materia") or row.get("catalog_materia"),
    )


def _parse_eso_alumno_curso(*, curso: str | None, nombre_grupo: str | None) -> int | None:
    curso_s = (curso or "").strip()
    grupo = (nombre_grupo or "").strip()

    if curso_s:
        m = re.search(r"(\d)", curso_s)
        if m:
            num = int(m.group(1))
            if num in PENDIENTES_ESO_ALUMNO_CURSOS:
                return num

    if grupo:
        m = re.match(r"^(\d)", grupo)
        if m:
            num = int(m.group(1))
            if num in PENDIENTES_ESO_ALUMNO_CURSOS:
                return num

    return None


def _parse_bach_alumno_curso(
    *,
    curso: str | None,
    nombre_grupo: str | None,
    estudio: str | None = None,
) -> int | None:
    """2º Bachillerato del alumno (curso, grupo o estudio)."""
    target = PENDIENTES_BACH_ALUMNO_CURSO
    curso_s = (curso or "").strip().lower()
    grupo = (nombre_grupo or "").strip()
    estudio_s = (estudio or "").strip().lower()

    if grupo and re.match(r"^6", grupo, re.IGNORECASE):
        return target

    if grupo and re.match(r"^2", grupo, re.IGNORECASE):
        if re.search(r"bach|bhs|bct", grupo, re.IGNORECASE):
            return target

    for text in (curso_s, estudio_s):
        if not text or ("eso" in text and "bach" not in text and "bhs" not in text and "bct" not in text):
            continue
        if re.search(r"\bfp\b|\bfpb\b|\bfpm\b", text):
            continue
        if not re.search(r"bach|bhs|bct|humanidades|bachillerato", text):
            continue
        m = re.search(r"(\d)", text)
        if m and int(m.group(1)) == target:
            return target

    return None


def _parse_bach_modalidad(
    *,
    curso: str | None,
    nombre_grupo: str | None,
    estudio: str | None,
) -> str | None:
    """Modalidad Bach 2º: bhs | bct."""
    if _parse_bach_alumno_curso(
        curso=curso, nombre_grupo=nombre_grupo, estudio=estudio
    ) != PENDIENTES_BACH_ALUMNO_CURSO:
        return None

    parts = [(curso or ""), (nombre_grupo or ""), (estudio or "")]
    text = " ".join(p for p in parts if p).lower()
    grupo_up = (nombre_grupo or "").upper()

    if re.search(r"\bbhs\b", text) or "humanidades" in text or "ciencias sociales" in text:
        if not re.search(r"\bbct\b", text) and "tecnolog" not in text:
            return "bhs"
    if re.search(r"\bbct\b", text) or ("ciencias" in text and "tecnolog" in text):
        if not re.search(r"\bbhs\b", text) and "humanidades" not in text:
            return "bct"
    if re.search(r"BHS", grupo_up):
        return "bhs"
    if re.search(r"BCT", grupo_up):
        return "bct"
    if "bhs" in text and "bct" not in text:
        return "bhs"
    if "bct" in text and "bhs" not in text:
        return "bct"
    return None


def _bach_modalidad_from_catalog(
    *,
    estudio: str | None,
    materia_abrev: str | None,
) -> str | None:
    return bach_pendiente_subject_modalidad(
        catalog_estudio=estudio,
        materia_abrev=materia_abrev,
    )


def _resolve_bach_pendiente_modalidad(row: dict[str, Any]) -> str | None:
    if _parse_bach_alumno_curso(
        curso=row.get("alumno_curso"),
        nombre_grupo=row.get("alumno_grupo"),
        estudio=row.get("alumno_estudio"),
    ) != PENDIENTES_BACH_ALUMNO_CURSO:
        return None
    return bach_pendiente_subject_modalidad(
        catalog_estudio=row.get("catalog_estudio"),
        materia_abrev=row.get("materia_abrev"),
    )


def _parse_fp_alumno_curso(
    *,
    etapa: str,
    curso: str | None,
    nombre_grupo: str | None,
) -> int | None:
    target = PENDIENTES_FP_ALUMNO_CURSO
    cycle = etapa.strip().lower()
    if cycle not in _FP_ETAPAS:
        return None

    curso_s = (curso or "").strip().lower()
    grupo = (nombre_grupo or "").strip()
    cycle_letter = cycle[-1]

    if curso_s:
        if cycle == "fpb" and re.search(
            r"(\d)\D*(?:fpb|fp\s*b|formacion\s+profesional\s+basica|formación\s+profesional\s+básica)",
            curso_s,
        ):
            m = re.search(r"(\d)", curso_s)
            if m and int(m.group(1)) == target:
                return target
        if cycle == "fpm" and re.search(
            r"(\d)\D*(?:fpm|fp\s*m|formacion\s+profesional\s+media|formación\s+profesional\s+media)",
            curso_s,
        ):
            m = re.search(r"(\d)", curso_s)
            if m and int(m.group(1)) == target:
                return target

    if grupo:
        m = re.match(rf"^fp{cycle_letter}(\d)", grupo, re.IGNORECASE)
        if m and int(m.group(1)) == target:
            return target

    return None


def _fetch_all_catalog() -> list[dict[str, Any]]:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT materia_abrev, materia, estudio, curso_asignatura, etapa
                FROM enrolled_subject_catalog
                WHERE materia_abrev IS NOT NULL
                  AND TRIM(materia_abrev) <> ''
                ORDER BY LOWER(materia_abrev), curso_asignatura
                """
            )
            return [dict(r) for r in cur.fetchall()]


def _catalog_entry(
    row: dict[str, Any], *, curso_asignatura: int, etapa: str
) -> dict[str, Any] | None:
    abrev = str(row.get("materia_abrev") or "").strip()
    if not abrev:
        return None
    ca_raw = row.get("curso_asignatura")
    if ca_raw is None or int(ca_raw) != curso_asignatura:
        return None
    row_etapa = _resolve_row_etapa(row)
    if row_etapa != etapa:
        return None
    materia = str(row.get("materia") or "").strip() or None
    return {
        "materia_abrev": abrev,
        "materia": materia,
        "curso_asignatura": curso_asignatura,
        "etapa": etapa,
        "label": _materia_label(materia=materia, materia_abrev=abrev, curso=curso_asignatura),
    }


def _catalog_rows_eso_matrix(all_catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for r in all_catalog:
        abrev = str(r.get("materia_abrev") or "").strip()
        ca_raw = r.get("curso_asignatura")
        if not abrev or ca_raw is None:
            continue
        ca = int(ca_raw)
        if not catalog_row_belongs_to_stage(
            etapa=r.get("etapa"),
            curso_asignatura=ca,
            stage="eso",
            estudio=r.get("estudio"),
            materia_abrev=abrev,
            materia=r.get("materia"),
        ):
            continue
        materia = str(r.get("materia") or "").strip() or None
        rows.append(
            {
                "materia_abrev": abrev,
                "materia": materia,
                "curso_asignatura": ca,
                "etapa": "eso",
                "label": _materia_label(materia=materia, materia_abrev=abrev, curso=ca),
            }
        )
    rows.sort(key=lambda x: normalize_for_sort(str(x["label"])))
    return rows


def _catalog_rows_bach_matrix(all_catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    _ = all_catalog
    return fetch_bach_pendientes_matrix_catalog()


def _catalog_rows_fp_matrix(all_catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for etapa in _FP_ETAPAS:
        stage_rows: list[dict[str, Any]] = []
        for r in all_catalog:
            entry = _catalog_entry(r, curso_asignatura=1, etapa=etapa)
            if entry:
                stage_rows.append(entry)
        stage_rows.sort(key=lambda x: normalize_for_sort(str(x["label"])))
        rows.extend(stage_rows)
    return rows


def _fetch_pendientes(import_id: int) -> list[dict[str, Any]]:
    if not import_id:
        return []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT
                    TRIM(es.materia_abrev) AS materia_abrev,
                    c.curso_asignatura,
                    c.etapa AS catalog_etapa,
                    c.estudio AS catalog_estudio,
                    c.materia AS catalog_materia,
                    TRIM(es.alumno) AS alumno,
                    {_ALUMNO_CURSO_RESUELTO_SQL} AS alumno_curso,
                    {_ALUMNO_GRUPO_RESUELTO_SQL} AS alumno_grupo,
                    es.estudio AS alumno_estudio
                FROM enrolled_subjects es
                INNER JOIN enrolled_subject_catalog c
                  ON TRIM(c.materia_abrev) = TRIM(es.materia_abrev)
                WHERE es.import_id = %s
                  AND TRIM(es.caracteristicas) = %s
                  AND TRIM(es.materia_abrev) <> ''
                  AND TRIM(es.alumno) <> ''
                """,
                (import_id, CARACTERISTICA_MATERIA_PENDIENTE),
            )
            return list(cur.fetchall())


def _alumnos_en_celda_matrix(
    entry: dict[str, Any],
    col_key: Any,
    alumnos_por_celda: dict[tuple[Any, ...], set[str]],
    cell_key_for_entry: Callable[[dict[str, Any], Any], tuple[Any, ...]],
) -> set[str]:
    alumnos: set[str] = set()
    materia_key = entry.get("pendientes_materia_key")
    if materia_key:
        alumnos |= alumnos_por_celda.get((materia_key, col_key), set())
    abrevs = entry.get("materia_abrevs")
    if abrevs:
        for abrev in abrevs:
            alumnos |= alumnos_por_celda.get((abrev, col_key), set())
    if alumnos:
        return alumnos
    return alumnos_por_celda.get(cell_key_for_entry(entry, col_key), set())


def _build_matrix_resumen(
    *,
    catalog_rows: list[dict[str, Any]],
    columns: list[dict[str, Any]],
    alumnos_por_celda: dict[tuple[Any, ...], set[str]],
    cell_key_for_entry: Callable[[dict[str, Any], Any], tuple[Any, ...]],
) -> dict[str, Any]:
    column_totals = {col["key"]: 0 for col in columns}
    table_rows: list[dict[str, Any]] = []
    grand_total = 0

    for entry in catalog_rows:
        counts: dict[Any, int] = {}
        row_total = 0
        for col in columns:
            col_key = col["key"]
            count = len(
                _alumnos_en_celda_matrix(
                    entry, col_key, alumnos_por_celda, cell_key_for_entry
                )
            )
            counts[col_key] = count
            row_total += count
            column_totals[col_key] += count
        table_rows.append(
            {
                "label": entry["label"],
                "materia": entry.get("materia"),
                "total": row_total,
                "counts": counts,
            }
        )
        grand_total += row_total

    return {
        "layout": "matrix",
        "columns": columns,
        "column_totals": column_totals,
        "grand_total": grand_total,
        "rows": table_rows,
    }


def _build_eso_pendientes_resumen(
    *,
    pendientes: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    alumnos_por_celda: dict[tuple[str, int, int], set[str]] = defaultdict(set)

    for row in pendientes:
        if not catalog_row_belongs_to_stage(
            etapa=row.get("catalog_etapa"),
            curso_asignatura=int(row["curso_asignatura"]),
            stage="eso",
            estudio=row.get("catalog_estudio"),
            materia_abrev=row.get("materia_abrev"),
            materia=row.get("catalog_materia"),
        ):
            continue
        alumno_curso = _parse_eso_alumno_curso(
            curso=row.get("alumno_curso"),
            nombre_grupo=row.get("alumno_grupo"),
        )
        if alumno_curso is None:
            continue
        abrev = str(row.get("materia_abrev") or "").strip()
        alumno = str(row.get("alumno") or "").strip()
        ca = row.get("curso_asignatura")
        if not abrev or not alumno or ca is None:
            continue
        alumnos_por_celda[(abrev, int(ca), alumno_curso)].add(alumno.lower())

    columns = _matrix_columns(PENDIENTES_ESO_ALUMNO_CURSOS)
    return _build_matrix_resumen(
        catalog_rows=catalog_rows,
        columns=columns,
        alumnos_por_celda=alumnos_por_celda,
        cell_key_for_entry=lambda entry, col_key: (
            entry["materia_abrev"],
            int(entry["curso_asignatura"]),
            col_key,
        ),
    )


def _consolidate_bach_matrix_resumen(resumen: dict[str, Any]) -> dict[str, Any]:
    return merge_bach_pendientes_matrix_resumen(resumen)


def _bach_pendiente_row_eligible(row: dict[str, Any]) -> bool:
    from db.enrolled_subject_catalog import bach_pendiente_row_eligible

    return bach_pendiente_row_eligible(row)


def _build_bach_pendientes_resumen(
    *,
    pendientes: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    from db.enrolled_subject_catalog import build_bach_pendientes_resumen

    _ = catalog_rows
    return build_bach_pendientes_resumen(pendientes)


def _build_fp_pendientes_resumen(
    *,
    pendientes: list[dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    alumnos_por_celda: dict[tuple[str, str, int], set[str]] = defaultdict(set)
    col_key = PENDIENTES_FP_ALUMNO_CURSO

    for row in pendientes:
        etapa = _resolve_row_etapa(row)
        if etapa not in _FP_ETAPAS:
            continue
        if int(row.get("curso_asignatura") or 0) != 1:
            continue
        alumno_curso = _parse_fp_alumno_curso(
            etapa=etapa,
            curso=row.get("alumno_curso"),
            nombre_grupo=row.get("alumno_grupo"),
        )
        if alumno_curso != col_key:
            continue
        abrev = str(row.get("materia_abrev") or "").strip()
        alumno = str(row.get("alumno") or "").strip()
        if not abrev or not alumno:
            continue
        alumnos_por_celda[(abrev, etapa, col_key)].add(alumno.lower())

    columns = _matrix_columns((col_key,))
    return _build_matrix_resumen(
        catalog_rows=catalog_rows,
        columns=columns,
        alumnos_por_celda=alumnos_por_celda,
        cell_key_for_entry=lambda entry, column_key: (
            entry["materia_abrev"],
            entry["etapa"],
            column_key,
        ),
    )


def _empty_resumen_for_table(table_key: str) -> dict[str, Any]:
    if table_key == "eso":
        return _empty_matrix_resumen(columns=_matrix_columns(PENDIENTES_ESO_ALUMNO_CURSOS))
    if table_key == "bach":
        return _empty_matrix_resumen(columns=_bach_matrix_columns())
    if table_key == "fp":
        return _empty_matrix_resumen(columns=_matrix_columns((PENDIENTES_FP_ALUMNO_CURSO,)))
    return _empty_matrix_resumen(columns=[])


def build_pendientes_resumenes() -> dict[str, dict[str, Any]]:
    ensure_subject_catalog_schema()
    if not get_catalog_meta():
        return {key: _empty_resumen_for_table(key) for key, _ in PENDIENTES_RESUMEN_TABLES}

    all_catalog = _fetch_all_catalog()
    import_id = _latest_import_id()
    pendientes = _fetch_pendientes(import_id) if import_id else []

    return {
        "eso": _build_eso_pendientes_resumen(
            pendientes=pendientes,
            catalog_rows=_catalog_rows_eso_matrix(all_catalog),
        ),
        "bach": _build_bach_pendientes_resumen(
            pendientes=pendientes,
            catalog_rows=_catalog_rows_bach_matrix(all_catalog),
        ),
        "fp": _build_fp_pendientes_resumen(
            pendientes=pendientes,
            catalog_rows=_catalog_rows_fp_matrix(all_catalog),
        ),
    }


def pendientes_resumen_titles() -> dict[str, str]:
    return {key: label for key, label in PENDIENTES_RESUMEN_TABLES}
