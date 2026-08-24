"""Catálogo abreviatura → curso de la asignatura (importación Excel independiente)."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Callable

from db.connection import get_db

CATALOG_EXCEL_HEADERS: tuple[str, ...] = (
    "MATERIA (abrev.)",
    "MATERIA",
    "ESTUDIO",
    "CURSO",
    "CURSO_ASIGN",
    "ETAPA",
    "DEPARTAMENTO",
    "HORAS",
)

CATALOG_FIELD_NAMES: tuple[str, ...] = (
    "materia_abrev",
    "materia",
    "estudio",
    "curso",
    "curso_asign",
    "etapa",
    "departamento",
    "horas",
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
    if (
        norm == "departamento"
        or norm in ("depto", "dpto", "dept")
        or norm.startswith("departamento")
    ):
        return "departamento"
    if (
        norm in ("horas", "hora", "h", "horas semanales", "horas semana")
        or (
            "hora" in norm
            and "horario" not in norm
            and "ahora" not in norm
        )
    ):
        return "horas"
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


def parse_horas_semanales(raw: str | None) -> int | None:
    """Horas semanales de la asignatura (entero positivo)."""
    t = (raw or "").strip().replace(",", ".")
    if not t:
        return None
    t = re.sub(r"\s+", " ", t)
    m = re.match(r"^(\d{1,2})(?:\.0+)?(?:\s*h(?:oras)?)?$", t, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        return n if n > 0 else None
    try:
        n = int(float(t))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def coerce_horas_semanales(raw: Any, phoras: Any = None) -> int | None:
    """Horas semanales desde catálogo (columna horas o, si falta, phoras × 30)."""
    if isinstance(raw, bool):
        raw = None
    if raw is not None and raw != "":
        if isinstance(raw, int):
            if raw > 0:
                return raw
        elif isinstance(raw, Decimal):
            try:
                n = int(raw)
            except (InvalidOperation, ValueError, OverflowError):
                n = None
            if n is not None and n > 0:
                return n
        elif isinstance(raw, float):
            if raw == raw and raw > 0:
                n = int(raw)
                if n > 0:
                    return n
        else:
            parsed = parse_horas_semanales(str(raw).strip())
            if parsed is not None:
                return parsed
    if phoras is None or phoras == "":
        return None
    try:
        p = Decimal(str(phoras).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if p <= 0:
        return None
    n = int((p * Decimal(30)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return n if n > 0 else None


def compute_phoras(horas: int | None) -> Decimal | None:
    """Peso horario: horas semanales / 30 (2 decimales, p. ej. 4 → 0,13)."""
    if horas is None:
        return None
    try:
        h = int(horas)
    except (TypeError, ValueError):
        return None
    if h <= 0:
        return None
    return (Decimal(h) / Decimal(30)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


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
    # Quitar puntuación habitual en etiquetas (E.S.O., 4º, etc.)
    compact = re.sub(r"[\s.º°/\-_]+", "", low)
    if re.search(r"grado\s*medio|\bfpm\b", low) or compact.startswith("fpm"):
        return "fpm"
    if re.search(r"grado\s*b[aá]sico|\bfpb\b", low) or compact.startswith("fpb"):
        return "fpb"
    if re.search(
        r"\bfp\b|formacion profesional|ciclo formativo",
        low,
    ) and "eso" not in compact:
        return None
    if (
        "eso" in low
        or "eso" in compact
        or "secundaria" in low
        or compact in {"eso", "eso1", "eso2", "eso3", "eso4"}
    ) and "bach" not in low and "bach" not in compact:
        return "eso"
    if "bach" in low or "bach" in compact or "bachillerato" in low:
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
    e_compact = re.sub(r"[\s.º°/\-_]+", "", e)
    if e in (
        "secundaria",
        "secundaria obligatoria",
        "e.s.o.",
        "educacion secundaria obligatoria",
    ) or "secundaria" in e or e_compact in {"eso", "eso1", "eso2", "eso3", "eso4"}:
        return "eso"
    if re.search(r"grado\s*medio|\bfpm\b", e) or e_compact.startswith("fpm"):
        return "fpm"
    if re.search(r"grado\s*b[aá]sico|\bfpb\b", e) or e_compact.startswith("fpb"):
        return "fpb"
    if "bach" in e or "bachillerato" in e:
        return "bach"
    if ("eso" in e or "eso" in e_compact) and "bach" not in e and "fp" not in e_compact:
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
    horas = parse_horas_semanales(row.get("horas"))
    return {
        "materia_abrev": abrev,
        "materia": materia,
        "estudio": estudio,
        "curso_asignatura": curso_asig,
        "etapa": etapa,
        "departamento": (row.get("departamento") or "").strip() or None,
        "horas": horas,
        "phoras": compute_phoras(horas),
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
            cur.execute(
                """
                ALTER TABLE enrolled_subject_catalog
                ADD COLUMN IF NOT EXISTS departamento TEXT
                """
            )
            cur.execute(
                """
                ALTER TABLE enrolled_subject_catalog
                ADD COLUMN IF NOT EXISTS horas SMALLINT
                """
            )
            cur.execute(
                """
                ALTER TABLE enrolled_subject_catalog
                ADD COLUMN IF NOT EXISTS phoras NUMERIC(8,4)
                """
            )
            # Solo rellena phoras si aún no está guardado. No reescribe en cada arranque.
            cur.execute(
                """
                UPDATE enrolled_subject_catalog
                SET phoras = ROUND((horas::numeric / 30), 2)
                WHERE horas IS NOT NULL AND horas > 0 AND phoras IS NULL
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
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT materia_abrev, departamento, horas
                FROM enrolled_subject_catalog
                """
            )
            prev = {
                str(r["materia_abrev"]).strip().casefold(): {
                    "departamento": (
                        str(r["departamento"]).strip()
                        if r.get("departamento")
                        else ""
                    ),
                    "horas": r.get("horas"),
                }
                for r in cur.fetchall()
                if r.get("materia_abrev")
            }

    entries: dict[str, dict[str, Any]] = {}
    skipped = 0
    hours_changed: list[tuple[str, int, str]] = []
    for row in rows:
        normalized = _normalize_catalog_row(row)
        if normalized is None:
            skipped += 1
            continue
        abrev_key = normalized["materia_abrev"].casefold()
        old = prev.get(abrev_key) or {}
        if not normalized.get("departamento") and old.get("departamento"):
            normalized["departamento"] = old["departamento"]
        if normalized.get("horas") is None and old.get("horas") is not None:
            try:
                normalized["horas"] = int(old["horas"])
            except (TypeError, ValueError):
                pass
        normalized["phoras"] = compute_phoras(normalized.get("horas"))
        try:
            old_h = int(old["horas"]) if old.get("horas") is not None else None
        except (TypeError, ValueError):
            old_h = None
        if old_h != normalized.get("horas"):
            etapa = (normalized.get("etapa") or "").strip().lower()
            curso = normalized.get("curso_asignatura")
            key = competencias_materia_group_key(normalized.get("materia") or "")
            if etapa and curso is not None and key:
                hours_changed.append((etapa, int(curso), key))
        entries[normalized["materia_abrev"]] = normalized

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM enrolled_subject_catalog")
            for entry in entries.values():
                cur.execute(
                    """
                    INSERT INTO enrolled_subject_catalog (
                        materia_abrev, materia, estudio, curso_asignatura,
                        etapa, departamento, horas, phoras, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        entry["materia_abrev"],
                        entry.get("materia"),
                        entry.get("estudio"),
                        entry["curso_asignatura"],
                        entry.get("etapa"),
                        entry.get("departamento"),
                        entry.get("horas"),
                        entry.get("phoras"),
                    ),
                )
    if hours_changed:
        from db.competencias_materia_variables import rebuild_variables_for_keys

        rebuild_variables_for_keys(hours_changed)
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


def list_catalog_preview(
    *,
    limit: int | None = 80,
    etapa: str | None = None,
    curso: int | None = None,
) -> list[dict[str, Any]]:
    ensure_subject_catalog_schema()
    where: list[str] = []
    params: list[Any] = []
    etapa_n = normalize_catalog_etapa(etapa) if etapa else None
    if etapa_n:
        where.append("LOWER(TRIM(COALESCE(etapa, ''))) = %s")
        params.append(etapa_n)
    if curso is not None:
        where.append("curso_asignatura = %s")
        params.append(int(curso))
    sql_where = (" WHERE " + " AND ".join(where)) if where else ""
    sql_limit = ""
    if limit is not None:
        sql_limit = " LIMIT %s"
        params.append(int(limit))
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT materia_abrev, materia, estudio, curso_asignatura,
                       etapa, departamento, horas, updated_at
                FROM enrolled_subject_catalog
                {sql_where}
                ORDER BY etapa NULLS LAST, curso_asignatura, LOWER(materia_abrev)
                {sql_limit}
                """,
                tuple(params),
            )
            return [dict(r) for r in cur.fetchall()]


def list_catalog_for_export() -> list[dict[str, Any]]:
    ensure_subject_catalog_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT materia_abrev, materia, estudio, curso_asignatura,
                       etapa, departamento, horas, phoras
                FROM enrolled_subject_catalog
                ORDER BY LOWER(materia_abrev), curso_asignatura
                """
            )
            return [dict(r) for r in cur.fetchall()]


def fetch_catalog_horas_index(
    stage: str,
) -> tuple[dict[tuple[int, str], int], dict[str, int], dict[str, int]]:
    """Horas del catálogo: (curso, materia_key), abreviatura y materia_key."""
    stage_n = (stage or "").strip().lower()
    by_group: dict[tuple[int, str], int] = {}
    by_abrev: dict[str, int] = {}
    by_key: dict[str, int] = {}
    if stage_n not in CANONICAL_CATALOG_ETAPAS:
        return by_group, by_abrev, by_key

    def _put(dest: dict, key: Any, horas_n: int) -> None:
        prev = dest.get(key)
        if prev is None or horas_n > prev:
            dest[key] = horas_n

    for row in list_catalog_for_export():
        resolved = resolve_catalog_stage(
            etapa=row.get("etapa"),
            estudio=row.get("estudio"),
            materia_abrev=row.get("materia_abrev"),
            materia=row.get("materia"),
        )
        if resolved != stage_n:
            continue
        try:
            curso = int(row.get("curso_asignatura") or 0)
        except (TypeError, ValueError):
            continue
        if curso <= 0:
            continue
        horas_n = coerce_horas_semanales(row.get("horas"), row.get("phoras"))
        if horas_n is None:
            continue
        key_name = competencias_materia_group_key(row.get("materia"))
        if key_name:
            _put(by_group, (curso, key_name), horas_n)
            if resolved == "bach":
                curso_ov = bach_competencias_curso_override(key_name)
                if curso_ov is not None and curso_ov != curso:
                    _put(by_group, (curso_ov, key_name), horas_n)
            _put(by_key, key_name, horas_n)
        abrev = (row.get("materia_abrev") or "").strip().lower()
        if abrev:
            _put(by_abrev, abrev, horas_n)
    return by_group, by_abrev, by_key


def sync_missing_catalog_horas(*, etapa: str | None = None) -> int:
    """Rellena horas NULL del catálogo copiando de filas hermanas o de phoras."""
    ensure_subject_catalog_schema()
    stage_filter = (etapa or "").strip().lower() or None
    if stage_filter and stage_filter not in CANONICAL_CATALOG_ETAPAS:
        return 0

    rows = list_catalog_for_export()
    donors_group: dict[tuple[str, int, str], int] = {}
    donors_key: dict[tuple[str, str], int] = {}
    parsed: list[tuple[dict[str, Any], str, int, int, str | None, int | None]] = []

    for row in rows:
        resolved = resolve_catalog_stage(
            etapa=row.get("etapa"),
            estudio=row.get("estudio"),
            materia_abrev=row.get("materia_abrev"),
            materia=row.get("materia"),
        )
        if not resolved:
            continue
        if stage_filter and resolved != stage_filter:
            continue
        try:
            curso = int(row.get("curso_asignatura") or 0)
        except (TypeError, ValueError):
            continue
        if curso <= 0:
            continue
        key_name = competencias_materia_group_key(row.get("materia"))
        horas_n = coerce_horas_semanales(row.get("horas"), row.get("phoras"))
        curso_canon = curso
        if resolved == "bach" and key_name:
            ov = bach_competencias_curso_override(key_name)
            if ov is not None:
                curso_canon = ov
        parsed.append((row, resolved, curso, curso_canon, key_name, horas_n))
        if horas_n is None or not key_name:
            continue
        g = (resolved, curso_canon, key_name)
        prev = donors_group.get(g)
        if prev is None or horas_n > prev:
            donors_group[g] = horas_n
        k = (resolved, key_name)
        prev_k = donors_key.get(k)
        if prev_k is None or horas_n > prev_k:
            donors_key[k] = horas_n

    updates: list[tuple[int, Decimal | None, str]] = []
    keys_changed: list[tuple[str, int, str]] = []
    for row, resolved, _curso, curso_canon, key_name, horas_n in parsed:
        if horas_n is not None and row.get("horas") is not None:
            continue
        found = horas_n
        if found is None and key_name:
            found = donors_group.get((resolved, curso_canon, key_name))
            if found is None:
                found = donors_key.get((resolved, key_name))
        if found is None:
            continue
        abrev = (row.get("materia_abrev") or "").strip()
        if not abrev:
            continue
        if row.get("horas") is not None and coerce_horas_semanales(row.get("horas")) == found:
            continue
        updates.append((found, compute_phoras(found), abrev))
        if key_name:
            keys_changed.append((resolved, curso_canon, key_name))

    if not updates:
        return 0

    with get_db() as conn:
        with conn.cursor() as cur:
            for horas_n, phoras_n, abrev in updates:
                cur.execute(
                    """
                    UPDATE enrolled_subject_catalog
                    SET horas = %s,
                        phoras = COALESCE(phoras, %s),
                        updated_at = NOW()
                    WHERE materia_abrev = %s
                      AND horas IS NULL
                    """,
                    (horas_n, phoras_n, abrev),
                )

    if keys_changed:
        from db.competencias_materia_variables import rebuild_variables_for_keys

        rebuild_variables_for_keys(keys_changed)
    return len(updates)


def persist_missing_horas_for_abrevs(abrevs: list[str], horas: int) -> int:
    """Escribe horas en filas del catálogo que aún las tienen vacías."""
    return persist_missing_horas_for_abrevs_bulk([(abrevs, horas)])


def persist_missing_horas_for_abrevs_bulk(
    items: list[tuple[list[str], int]],
) -> int:
    """Escribe horas vacías del catálogo en una sola transacción."""
    params: list[tuple[int, Any, str]] = []
    seen: set[str] = set()
    for abrevs, horas in items:
        horas_n = coerce_horas_semanales(horas)
        if horas_n is None:
            continue
        phoras_n = compute_phoras(horas_n)
        for abrev in abrevs or []:
            a = (abrev or "").strip()
            if not a or a.casefold() in seen:
                continue
            seen.add(a.casefold())
            params.append((horas_n, phoras_n, a))
    if not params:
        return 0
    n = 0
    with get_db() as conn:
        with conn.cursor() as cur:
            for horas_n, phoras_n, abrev in params:
                cur.execute(
                    """
                    UPDATE enrolled_subject_catalog
                    SET horas = %s,
                        phoras = COALESCE(phoras, %s),
                        updated_at = NOW()
                    WHERE materia_abrev = %s
                      AND horas IS NULL
                    """,
                    (horas_n, phoras_n, abrev),
                )
                n += int(cur.rowcount or 0)
    return n


def map_departamento_desde_matriculas() -> dict[str, str]:
    """Abreviatura (lower) → departamento según la última importación de matrículas."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (LOWER(TRIM(materia_abrev)))
                    LOWER(TRIM(materia_abrev)) AS abrev_key,
                    TRIM(departamento) AS departamento
                FROM enrolled_subjects
                WHERE TRIM(COALESCE(materia_abrev, '')) <> ''
                  AND TRIM(COALESCE(departamento, '')) <> ''
                ORDER BY LOWER(TRIM(materia_abrev)), import_id DESC, row_number
                """
            )
            return {
                str(r["abrev_key"]): str(r["departamento"]).strip()
                for r in cur.fetchall()
                if r.get("abrev_key") and r.get("departamento")
            }


def catalog_materia_group_key(materia: str | None) -> str | None:
    """Clave de agrupación Bach: solo columna MATERIA (ignora estudio y abreviatura)."""
    return _catalog_materia_group_key(materia)


def competencias_materia_group_key(materia: str | None) -> str | None:
    """Clave para listado/criterios de competencias: unifica alias habituales.

    - Francés / «Segunda Lengua Extranjera: Francés» → segunda lengua extranjera
    - Inglés → lengua extranjera
    - TIC / variantes del nombre largo → un solo nombre
    - Matemáticas aplicadas a las CCSS ↔ Ciencias Sociales
    - Enseñanza Religiosa Evangélica → religión evangélica
    """
    key = _catalog_materia_group_key(materia)
    if not key:
        return None
    if key == "frances" or "segunda lengua extranjera" in key:
        return "segunda lengua extranjera"
    if key == "ingles" or key == "lengua extranjera":
        return "lengua extranjera"
    if key == "tic" or key.startswith("tecnologias de la informacion"):
        return "tecnologias de la informacion y la comunicacion"
    if "matematicas aplicadas" in key and (
        "ccss" in key or "ciencias sociales" in key
    ):
        return "matematicas aplicadas a las ciencias sociales"
    if key in ("ensenanza religiosa evangelica", "religion evangelica"):
        return "religion evangelica"
    return key


# Etiquetas canónicas en el listado de competencias (curso → nombre con I/II).
BACH_COMPETENCIAS_CANONICAL_LABELS: dict[tuple[str, int], str] = {
    ("segunda lengua extranjera", 1): "Segunda Lengua Extranjera I",
    ("segunda lengua extranjera", 2): "Segunda Lengua Extranjera II",
    ("lengua extranjera", 1): "Lengua Extranjera I",
    ("lengua extranjera", 2): "Lengua Extranjera II",
    (
        "matematicas aplicadas a las ciencias sociales",
        1,
    ): "Matemáticas aplicadas a las Ciencias Sociales I",
    (
        "matematicas aplicadas a las ciencias sociales",
        2,
    ): "Matemáticas aplicadas a las Ciencias Sociales II",
    ("tecnologias de la informacion y la comunicacion", 1): (
        "Tecnologías de la Información y la Comunicación I"
    ),
    ("tecnologias de la informacion y la comunicacion", 2): (
        "Tecnologías de la Información y la Comunicación II"
    ),
    ("religion evangelica", 1): "Religión Evangélica",
}

# Curso correcto cuando el catálogo Neon o una semilla antigua lo tenían mal.
BACH_COMPETENCIAS_CURSO_OVERRIDES: dict[str, int] = {
    "historia de la musica y de la danza": 2,
}

_BACH_COURSE_ROMAN = {1: "I", 2: "II", 3: "III"}


def bach_competencias_curso_override(materia_key: str | None) -> int | None:
    """Curso canónico Bach si difiere del catálogo (p. ej. Historia de la Música → 2º)."""
    raw = (materia_key or "").strip()
    if not raw:
        return None
    canonical = competencias_materia_group_key(raw) or raw
    return BACH_COMPETENCIAS_CURSO_OVERRIDES.get(canonical)


def _fix_bach_roman_for_curso(label: str, curso: int) -> str:
    """Ajusta el numeral final al curso (p. ej. «… Francés I» en 2º → «… II»)."""
    roman = _BACH_COURSE_ROMAN.get(int(curso))
    if not roman:
        return label
    base = strip_bach_roman_suffix(label)
    if not base:
        return label
    # Solo reescribe si ya había numeral o es familia con I/II canónico.
    if _BACH_ROMAN_SUFFIX_RE.search(label or ""):
        return f"{base} {roman}"
    return label


def bach_competencias_canonical_label(
    materia_key: str,
    curso: int,
    current: str | None = None,
) -> str:
    """Nombre a mostrar; canónico por curso (corrige «Francés I» en 2º → II)."""
    cur = (current or "").strip()
    key = (materia_key or "").strip()
    canon = BACH_COMPETENCIAS_CANONICAL_LABELS.get((key, int(curso)))
    if canon:
        return canon
    if ":" in cur:
        return _fix_bach_roman_for_curso(cur, curso)
    return cur


def is_bach_religion_materia_key(materia_key: str | None) -> bool:
    """Religión (cualquier confesión) — no se oferta en 2º Bachillerato."""
    key = (materia_key or "").strip()
    return key.startswith("religion") or "religiosa" in key


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


_BACH_ROMAN_SUFFIX_RE = re.compile(r"\s+(I{1,3})\s*$", re.IGNORECASE)


def strip_bach_roman_suffix(materia: str | None) -> str:
    """«Griego I» / «Latín II» → base sin numeral romano de curso."""
    raw = re.sub(r"\s+", " ", (materia or "").replace("\u00a0", " ")).strip()
    if not raw:
        return ""
    return _BACH_ROMAN_SUFFIX_RE.sub("", raw).strip()


def _catalog_materia_group_key(materia: str | None) -> str | None:
    from utils.text import normalize_for_sort

    raw = strip_bach_roman_suffix(materia)
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
