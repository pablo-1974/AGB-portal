"""Catálogo abreviatura → curso de la asignatura (importación Excel independiente)."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable

from db.connection import get_db

CATALOG_EXCEL_HEADERS: tuple[str, ...] = (
    "MATERIA (abrev.)",
    "MATERIA",
    "ESTUDIO",
    "CURSO",
    "CURSO_ASIGN",
    "ETAPA",
)

CATALOG_FIELD_NAMES: tuple[str, ...] = (
    "materia_abrev",
    "materia",
    "estudio",
    "curso",
    "curso_asign",
    "etapa",
)

CATALOG_FIELD_TO_EXCEL: dict[str, str] = dict(
    zip(CATALOG_FIELD_NAMES, CATALOG_EXCEL_HEADERS)
)


def _norm_header(value: object) -> str:
    text = str(value or "").strip().lower()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    return " ".join(text.split())


def _header_to_field(norm: str) -> str | None:
    if not norm:
        return None
    if "materia" in norm and "abrev" in norm:
        return "materia_abrev"
    if norm == "materia":
        return "materia"
    if norm == "etapa":
        return "etapa"
    if norm == "estudio":
        return "estudio"
    if "curso" in norm and "asign" in norm:
        return "curso_asign"
    if norm == "curso":
        return "curso"
    return None


def map_catalog_headers_to_fields(headers: list[str]) -> dict[int, str]:
    idx_to_field: dict[int, str] = {}
    used: set[str] = set()
    for pos, raw in enumerate(headers):
        field = _header_to_field(_norm_header(raw))
        if field is None or field in used:
            continue
        idx_to_field[pos] = field
        used.add(field)
    return idx_to_field


def find_catalog_header_row(
    ws, *, max_scan: int = 30
) -> tuple[int, list[str]] | None:
    for row_idx, row in enumerate(
        ws.iter_rows(min_row=1, max_row=max_scan, values_only=True), start=1
    ):
        if not row:
            continue
        headers = [str(c).strip() if c is not None else "" for c in row]
        mapped = map_catalog_headers_to_fields(headers)
        if "materia_abrev" in mapped.values() and "curso_asign" in mapped.values():
            return row_idx, headers
    return None


def _row_from_values(
    *,
    values: tuple[object, ...],
    idx_to_field: dict[int, str],
) -> dict[str, str | None]:
    record = {name: None for name in CATALOG_FIELD_NAMES}
    for pos, field in idx_to_field.items():
        raw = values[pos] if pos < len(values) else None
        if raw is None:
            record[field] = None
        elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
            record[field] = str(int(raw) if float(raw).is_integer() else raw).strip() or None
        else:
            s = str(raw).strip()
            record[field] = s if s else None
    return record


def parse_catalog_worksheet_rows(ws) -> tuple[dict[int, str], list[dict[str, str | None]]]:
    found = find_catalog_header_row(ws)
    if not found:
        return {}, []
    header_row_idx, headers = found
    idx_to_field = map_catalog_headers_to_fields(headers)
    if "materia_abrev" not in idx_to_field.values():
        return idx_to_field, []

    parsed: list[dict[str, str | None]] = []
    for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
        if not row or all(
            c is None or (isinstance(c, str) and not c.strip()) for c in row
        ):
            continue
        record = _row_from_values(values=row, idx_to_field=idx_to_field)
        if not (record.get("materia_abrev") or "").strip():
            continue
        parsed.append(record)
    return idx_to_field, parsed


def parse_catalog_workbook_rows(
    wb,
) -> tuple[dict[int, str], list[dict[str, str | None]]]:
    best_idx: dict[int, str] = {}
    best_rows: list[dict[str, str | None]] = []
    for sheet_name in wb.sheetnames:
        idx_to_field, rows = parse_catalog_worksheet_rows(wb[sheet_name])
        if "materia_abrev" not in idx_to_field.values():
            continue
        if len(rows) > len(best_rows):
            best_idx = idx_to_field
            best_rows = rows
    return best_idx, best_rows


def parse_curso_asignatura(raw: str | None) -> int | None:
    t = (raw or "").strip()
    if not t:
        return None
    if re.fullmatch(r"\d{1,2}", t):
        return int(t)
    m = re.match(r"^(\d{1,2})\s*[º°]?\s*$", t, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d)", t)
    if m:
        return int(m.group(1))
    return None


CANONICAL_CATALOG_ETAPAS: frozenset[str] = frozenset({"eso", "bach", "fpb", "fpm"})

CATALOG_STAGE_KEYS: tuple[tuple[str, str], ...] = (
    ("eso", "ESO"),
    ("bach", "BACHILLERATO"),
    ("fpb", "FPB"),
    ("fpm", "FPM"),
)

CATALOG_ETAPA_EXPORT_LABELS: dict[str, str] = {
    "eso": "ESO",
    "bach": "BACH",
    "fpb": "FPB",
    "fpm": "FPM",
}


def etapa_from_estudio(estudio: str | None) -> str | None:
    e = (estudio or "").strip()
    if not e:
        return None
    low = e.lower()
    low = "".join(
        c for c in unicodedata.normalize("NFD", low) if unicodedata.category(c) != "Mn"
    )
    if re.search(r"grado\s*medio|\bfpm\b", low):
        return "fpm"
    if re.search(r"grado\s*b[aá]sico|\bfpb\b", low):
        return "fpb"
    if re.search(r"\bfp\b|formacion profesional|formación profesional|ciclo formativo", low):
        return None
    if "eso" in low and "bach" not in low and "fp" not in low:
        return "eso"
    if "bach" in low:
        return "bach"
    return None


# Cursos de asignatura válidos al importar el catálogo en Neon (todas las etapas completas).
CATALOG_COURSE_NUMS: dict[str, tuple[int, ...]] = {
    "eso": (1, 2, 3, 4),
    "bach": (1, 2),
    "fpb": (1, 2),
    "fpm": (1, 2),
}

# Cursos que entran en el resumen de pendientes (Listados → Asignaturas).
# ESO: solo asignaturas de 1º a 3º; el catálogo en Neon sí incluye 4º ESO.
PENDIENTES_RESUMEN_COURSE_NUMS: dict[str, tuple[int, ...]] = {
    "eso": (1, 2, 3),
    "bach": (1, 2),
    "fpb": (1, 2),
    "fpm": (1, 2),
}


def normalize_catalog_etapa(etapa: str | None) -> str | None:
    """Normaliza columna ETAPA del Excel o Neon → eso | bach | fpb | fpm."""
    e = (etapa or "").strip().lower()
    if not e:
        return None
    if e in CANONICAL_CATALOG_ETAPAS:
        return e
    if e == "bachillerato":
        return "bach"
    if e in ("secundaria", "secundaria obligatoria", "e.s.o.", "educacion secundaria obligatoria"):
        return "eso"
    if re.search(r"grado\s*medio|\bfpm\b", e):
        return "fpm"
    if re.search(r"grado\s*b[aá]sico|\bfpb\b", e):
        return "fpb"
    if "bach" in e:
        return "bach"
    if "eso" in e and "bach" not in e and "fp" not in e:
        return "eso"
    return None


def resolve_catalog_stage(
    *,
    etapa: str | None,
    estudio: str | None = None,
    materia_abrev: str | None = None,
    materia: str | None = None,
) -> str | None:
    """Etapa canónica de una fila del catálogo (eso | bach | fpb | fpm)."""
    resolved = normalize_catalog_etapa(etapa)
    if resolved:
        return resolved
    # Compatibilidad con filas antiguas sin columna ETAPA en el Excel
    return etapa_from_estudio(estudio)


def catalog_row_belongs_to_stage(
    *,
    etapa: str | None,
    curso_asignatura: int,
    stage: str,
    estudio: str | None = None,
    materia_abrev: str | None = None,
    materia: str | None = None,
) -> bool:
    allowed = PENDIENTES_RESUMEN_COURSE_NUMS.get(stage, ())
    if curso_asignatura not in allowed:
        return False
    row_stage = resolve_catalog_stage(
        etapa=etapa,
        estudio=estudio,
        materia_abrev=materia_abrev,
        materia=materia,
    )
    return row_stage == stage


def _normalize_catalog_row(row: dict[str, str | None]) -> dict[str, Any] | None:
    abrev = (row.get("materia_abrev") or "").strip()
    if not abrev:
        return None
    curso_asig = parse_curso_asignatura(row.get("curso_asign"))
    if curso_asig is None:
        return None
    materia = (row.get("materia") or "").strip() or None
    estudio = (row.get("estudio") or "").strip() or None
    etapa_input = (row.get("etapa") or "").strip() or None
    etapa = normalize_catalog_etapa(etapa_input)
    if etapa is None:
        etapa = etapa_from_estudio(estudio)
    if etapa is None:
        return None
    allowed = CATALOG_COURSE_NUMS.get(etapa, ())
    if curso_asig not in allowed:
        return None
    return {
        "materia_abrev": abrev,
        "materia": materia,
        "estudio": estudio,
        "curso_asignatura": curso_asig,
        "etapa": etapa,
    }


_catalog_schema_ready = False


def ensure_subject_catalog_schema() -> None:
    global _catalog_schema_ready
    if _catalog_schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS enrolled_subject_catalog (
                    materia_abrev TEXT NOT NULL PRIMARY KEY,
                    materia TEXT,
                    estudio TEXT,
                    curso_asignatura SMALLINT NOT NULL,
                    etapa TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                ALTER TABLE enrolled_subject_catalog
                ADD COLUMN IF NOT EXISTS estudio TEXT
                """
            )
    _catalog_schema_ready = True


def replace_subject_catalog(
    rows: list[dict[str, str | None]],
) -> tuple[int, int]:
    """
    Sustituye el catálogo completo.

    Returns:
        (filas insertadas, filas omitidas por datos inválidos)
    """
    ensure_subject_catalog_schema()
    entries: dict[str, dict[str, Any]] = {}
    skipped = 0
    for row in rows:
        normalized = _normalize_catalog_row(row)
        if normalized is None:
            skipped += 1
            continue
        entries[normalized["materia_abrev"]] = normalized

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM enrolled_subject_catalog")
            for entry in entries.values():
                cur.execute(
                    """
                    INSERT INTO enrolled_subject_catalog (
                        materia_abrev, materia, estudio, curso_asignatura, etapa, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        entry["materia_abrev"],
                        entry.get("materia"),
                        entry.get("estudio"),
                        entry["curso_asignatura"],
                        entry.get("etapa"),
                    ),
                )
    return len(entries), skipped


def get_catalog_meta() -> dict[str, Any] | None:
    ensure_subject_catalog_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)::int AS row_count,
                       MAX(updated_at) AS updated_at
                FROM enrolled_subject_catalog
                """
            )
            row = cur.fetchone()
    if not row or int(row["row_count"] or 0) == 0:
        return None
    updated = row.get("updated_at")
    return {
        "row_count": int(row["row_count"]),
        "updated_at": updated,
    }


def list_catalog_preview(*, limit: int = 80) -> list[dict[str, Any]]:
    ensure_subject_catalog_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT materia_abrev, materia, estudio, curso_asignatura, etapa, updated_at
                FROM enrolled_subject_catalog
                ORDER BY LOWER(materia_abrev)
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(r) for r in cur.fetchall()]


def list_catalog_for_export() -> list[dict[str, Any]]:
    ensure_subject_catalog_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT materia_abrev, materia, estudio, curso_asignatura, etapa
                FROM enrolled_subject_catalog
                ORDER BY LOWER(materia_abrev), curso_asignatura
                """
            )
            return [dict(r) for r in cur.fetchall()]


def catalog_materia_group_key(materia: str | None) -> str | None:
    """Clave de agrupación Bach: solo columna MATERIA (ignora estudio y abreviatura)."""
    return _catalog_materia_group_key(materia)


def bach_modalidad_from_materia_abrev(materia_abrev: str | None) -> str | None:
    """Columna BHS/BCT según la abreviatura del catálogo (p. ej. BHS-1-ING1)."""
    abrev = (materia_abrev or "").strip().upper()
    if not abrev:
        return None
    if re.match(r"BCT(?:[-_/]|$)", abrev) or re.search(r"(?:^|[-_/])BCT(?:[-_/]|$)", abrev):
        return "bct"
    if re.match(r"BHS(?:[-_/]|$)", abrev) or re.search(r"(?:^|[-_/])BHS(?:[-_/]|$)", abrev):
        return "bhs"
    return None


def bach_modalidad_from_catalog_estudio(catalog_estudio: str | None) -> str | None:
    """Modalidad BHS/BCT solo a partir del estudio de la asignatura en catálogo."""
    low = (catalog_estudio or "").strip().lower()
    if not low:
        return None
    if re.search(r"\bbct\b", low) or "tecnolog" in low:
        return "bct"
    if (
        re.search(r"\bbhs\b", low)
        or "humanidades" in low
        or "ciencias sociales" in low
    ):
        return "bhs"
    return None


def bach_pendiente_subject_modalidad(
    *,
    catalog_estudio: str | None,
    materia_abrev: str | None,
) -> str | None:
    """Modalidad BHS/BCT de la asignatura pendiente (nunca del alumno)."""
    modalidad = bach_modalidad_from_materia_abrev(materia_abrev)
    if modalidad:
        return modalidad
    return bach_modalidad_from_catalog_estudio(catalog_estudio)


def bach_pendientes_matrix_columns() -> list[dict[str, Any]]:
    return [{"key": "bhs", "label": "BHS"}, {"key": "bct", "label": "BCT"}]


BACH_PENDIENTES_ALUMNO_CURSO = 2


def parse_bach_pendiente_alumno_curso(
    *,
    curso: str | None,
    nombre_grupo: str | None,
    estudio: str | None = None,
) -> int | None:
    """2º Bachillerato del alumno (curso, grupo o estudio)."""
    target = BACH_PENDIENTES_ALUMNO_CURSO
    curso_s = (curso or "").strip().lower()
    grupo = (nombre_grupo or "").strip()
    estudio_s = (estudio or "").strip().lower()

    if grupo and re.match(r"^6", grupo, re.IGNORECASE):
        return target

    if grupo and re.match(r"^2", grupo, re.IGNORECASE):
        if re.search(r"bach|bhs|bct", grupo, re.IGNORECASE):
            return target

    for text in (curso_s, estudio_s):
        if not text or (
            "eso" in text and "bach" not in text and "bhs" not in text and "bct" not in text
        ):
            continue
        if re.search(r"\bfp\b|\bfpb\b|\bfpm\b", text):
            continue
        if not re.search(r"bach|bhs|bct|humanidades|bachillerato", text):
            continue
        m = re.search(r"(\d)", text)
        if m and int(m.group(1)) == target:
            return target

    return None


def bach_pendiente_row_eligible(row: dict[str, Any]) -> bool:
    etapa = resolve_catalog_stage(
        etapa=row.get("etapa") or row.get("catalog_etapa"),
        estudio=row.get("estudio") or row.get("catalog_estudio"),
        materia_abrev=row.get("materia_abrev"),
        materia=row.get("materia") or row.get("catalog_materia"),
    )
    if etapa != "bach":
        return False
    if int(row.get("curso_asignatura") or 0) != 1:
        return False
    return (
        parse_bach_pendiente_alumno_curso(
            curso=row.get("alumno_curso"),
            nombre_grupo=row.get("alumno_grupo"),
            estudio=row.get("alumno_estudio"),
        )
        == BACH_PENDIENTES_ALUMNO_CURSO
    )


def build_bach_pendientes_resumen(pendientes: list[dict[str, Any]]) -> dict[str, Any]:
    """Resumen matriz Bach pendientes (catálogo unificado + columnas BHS/BCT)."""
    return build_bach_pendientes_matrix_resumen(
        pendientes,
        catalog_rows=fetch_bach_pendientes_matrix_catalog(),
        row_eligible=bach_pendiente_row_eligible,
        columns=bach_pendientes_matrix_columns(),
    )


def bach_alumnos_en_celda_matrix(
    entry: dict[str, Any],
    col_key: str,
    alumnos_por_celda: dict[tuple[Any, ...], set[str]],
) -> set[str]:
    """Alumnos en celda Bach: abreviaturas BHS/BCT van a su columna correspondiente."""
    alumnos: set[str] = set()
    materia_key = entry.get("pendientes_materia_key")
    if materia_key:
        alumnos |= alumnos_por_celda.get((materia_key, col_key), set())
    for abrev in entry.get("materia_abrevs") or []:
        abrev_s = str(abrev or "").strip()
        if not abrev_s:
            continue
        if bach_modalidad_from_materia_abrev(abrev_s) == col_key:
            alumnos |= alumnos_por_celda.get((abrev_s, col_key), set())
        elif bach_modalidad_from_materia_abrev(abrev_s) is None:
            alumnos |= alumnos_por_celda.get((abrev_s, col_key), set())
    if alumnos:
        return alumnos
    abrev = str(entry.get("materia_abrev") or "").strip()
    if abrev:
        return alumnos_por_celda.get((abrev, col_key), set())
    return set()


def build_bach_pendientes_matrix_resumen(
    pendientes: list[dict[str, Any]],
    *,
    catalog_rows: list[dict[str, Any]],
    row_eligible: Callable[[dict[str, Any]], bool],
    columns: list[dict[str, Any]],
) -> dict[str, Any]:
    """Matriz Bach 1º pendientes: filas unificadas por materia, columnas BHS/BCT."""
    alumnos_por_celda: dict[tuple[str, str], set[str]] = defaultdict(set)

    for row in pendientes:
        if not row_eligible(row):
            continue
        modalidad = bach_pendiente_subject_modalidad(
            catalog_estudio=row.get("catalog_estudio"),
            materia_abrev=row.get("materia_abrev"),
        )
        if modalidad is None:
            continue
        alumno = str(row.get("alumno") or "").strip()
        abrev = str(row.get("materia_abrev") or "").strip()
        materia_key = catalog_materia_group_key(row.get("catalog_materia"))
        if not alumno or (not materia_key and not abrev):
            continue
        alumno_id = alumno.lower()
        if materia_key:
            alumnos_por_celda[(materia_key, modalidad)].add(alumno_id)
        if abrev:
            alumnos_por_celda[(abrev, modalidad)].add(alumno_id)

    column_totals = {col["key"]: 0 for col in columns}
    table_rows: list[dict[str, Any]] = []
    grand_total = 0

    for entry in catalog_rows:
        counts: dict[str, int] = {}
        row_total = 0
        for col in columns:
            col_key = col["key"]
            count = len(
                bach_alumnos_en_celda_matrix(entry, col_key, alumnos_por_celda)
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

    resumen = {
        "layout": "matrix",
        "columns": columns,
        "column_totals": column_totals,
        "grand_total": grand_total,
        "rows": table_rows,
    }
    return merge_bach_pendientes_matrix_resumen(resumen)


def _catalog_materia_group_key(materia: str | None) -> str | None:
    from utils.text import normalize_for_sort

    raw = re.sub(r"\s+", " ", (materia or "").replace("\u00a0", " ")).strip()
    if not raw:
        return None
    raw = unicodedata.normalize("NFC", raw)
    return normalize_for_sort(raw)


def fetch_bach_pendientes_matrix_catalog() -> list[dict[str, Any]]:
    """Catálogo Bach 1º: una fila por materia (unifica modalidades BHS/BCT)."""
    ensure_subject_catalog_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT materia_abrev, materia, estudio, etapa, curso_asignatura
                FROM enrolled_subject_catalog
                WHERE curso_asignatura = 1
                  AND materia IS NOT NULL
                  AND TRIM(materia) <> ''
                  AND TRIM(materia_abrev) <> ''
                ORDER BY LOWER(TRIM(materia)), materia_abrev
                """
            )
            raw_rows = [dict(r) for r in cur.fetchall()]

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in raw_rows:
        if not catalog_row_belongs_to_stage(
            etapa=row.get("etapa"),
            curso_asignatura=1,
            stage="bach",
            estudio=row.get("estudio"),
            materia_abrev=row.get("materia_abrev"),
            materia=row.get("materia"),
        ):
            continue
        key = _catalog_materia_group_key(row.get("materia"))
        if not key:
            continue
        groups.setdefault(key, []).append(row)

    catalog_rows: list[dict[str, Any]] = []
    for items in groups.values():
        abrevs: list[str] = []
        materia = ""
        for row in items:
            abrev = str(row.get("materia_abrev") or "").strip()
            if abrev and abrev not in abrevs:
                abrevs.append(abrev)
            text = str(row.get("materia") or "").strip()
            if text:
                materia = text
        if not abrevs or not materia:
            continue
        catalog_rows.append(
            {
                "materia_abrev": abrevs[0],
                "materia_abrevs": abrevs,
                "materia": materia,
                "pendientes_materia_key": _catalog_materia_group_key(materia),
                "curso_asignatura": 1,
                "etapa": "bach",
                "label": f"{materia} (1º)",
            }
        )

    catalog_rows.sort(
        key=lambda row: _catalog_materia_group_key(row.get("materia")) or ""
    )
    return catalog_rows


def merge_bach_pendientes_matrix_resumen(resumen: dict[str, Any]) -> dict[str, Any]:
    """Fusiona filas duplicadas del resumen Bach por materia."""
    if not resumen or resumen.get("layout") != "matrix":
        return resumen

    columns = resumen.get("columns") or []
    rows_in = resumen.get("rows") or []
    if not rows_in:
        return resumen

    merged: dict[str, dict[str, Any]] = {}
    for row in rows_in:
        materia = str(row.get("materia") or "").strip()
        if not materia:
            label = str(row.get("label") or "")
            materia = re.sub(r"\s*\(\d+º\)\s*$", "", label).strip()
        key = _catalog_materia_group_key(materia)
        if not key:
            key = str(row.get("label") or "")
        if key not in merged:
            merged[key] = {
                "label": f"{materia} (1º)" if materia else str(row.get("label") or ""),
                "materia": materia or row.get("materia"),
                "total": 0,
                "counts": {col["key"]: 0 for col in columns},
            }
        dest = merged[key]
        dest["total"] += int(row.get("total") or 0)
        for col in columns:
            dest["counts"][col["key"]] += int(row["counts"].get(col["key"], 0))

    rows_out = sorted(
        merged.values(),
        key=lambda row: _catalog_materia_group_key(row.get("materia")) or "",
    )
    column_totals = {
        col["key"]: sum(int(row["counts"].get(col["key"], 0)) for row in rows_out)
        for col in columns
    }
    return {
        **resumen,
        "rows": rows_out,
        "column_totals": column_totals,
        "grand_total": sum(column_totals.values()),
    }
