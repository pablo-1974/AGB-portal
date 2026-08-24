"""Criterios de evaluación por materia (solo códigos + cruces con descriptores)."""

from __future__ import annotations

import re
from typing import Any

from db.connection import get_db
from db.competencias_criterios_seeds_bach import SEED_BACH
from db.competencias_criterios_seeds_eso import SEED_ESO
from db.enrolled_subject_catalog import (
    BACH_COMPETENCIAS_CURSO_OVERRIDES,
    competencias_materia_group_key,
)

TABLE = "competencias_materia_criterios"

# Orden de columnas en la matriz de cruces.
COMP_CLAVE_COLS: tuple[str, ...] = (
    "CCL",
    "CP",
    "STEM",
    "CD",
    "CPSAA",
    "CC",
    "CE",
    "CCEC",
)

_schema_ready = False


def normalize_descriptor_code(raw: str) -> str:
    """CCL1 / CCL 1 / ccl1 → «CCL 1»; CPSAA1.1 → «CPSAA 1.1»."""
    s = re.sub(r"\s+", "", (raw or "").strip().upper())
    m = re.match(
        r"^(CCL|CP|STEM|CD|CPSAA|CC|CE|CCEC)(\d+(?:\.\d+)?)$",
        s,
        re.IGNORECASE,
    )
    if m:
        return f"{m.group(1).upper()} {m.group(2)}"
    spaced = (raw or "").strip().upper()
    m2 = re.match(
        r"^(CCL|CP|STEM|CD|CPSAA|CC|CE|CCEC)\s+(\d+(?:\.\d+)?)$",
        spaced,
        re.IGNORECASE,
    )
    if m2:
        return f"{m2.group(1).upper()} {m2.group(2)}"
    return (raw or "").strip()


def _criterio_ce(criterio: str) -> int:
    head = (criterio or "").split(".", 1)[0]
    try:
        return int(head)
    except ValueError:
        return 0


def _sort_criterio(criterio: str) -> tuple[int, float]:
    parts = (criterio or "").split(".")
    try:
        major = int(parts[0])
    except ValueError:
        major = 0
    try:
        minor = float(parts[1]) if len(parts) > 1 else 0.0
    except ValueError:
        minor = 0.0
    return (major, minor)


def ensure_competencias_materia_criterios_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    etapa TEXT NOT NULL,
                    curso_asignatura SMALLINT NOT NULL,
                    materia_key TEXT NOT NULL,
                    materia_nombre TEXT NOT NULL,
                    criterio TEXT NOT NULL,
                    competencia_especifica SMALLINT NOT NULL,
                    descriptores TEXT[] NOT NULL DEFAULT '{{}}',
                    PRIMARY KEY (etapa, curso_asignatura, materia_key, criterio)
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_cmc_materia
                ON {TABLE} (etapa, curso_asignatura, materia_key)
                """
            )
    _seed_bach_criterios()
    _seed_eso_criterios()
    _migrate_bach_curso_overrides()
    _schema_ready = True


def _migrate_bach_curso_overrides() -> None:
    """Mueve filas guardadas con curso erróneo (p. ej. Historia Música y Danza en 1º)."""
    if not BACH_COMPETENCIAS_CURSO_OVERRIDES:
        return
    etapa = "bach"
    tables: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("competencias_materia_criterios", ("criterio",)),
        ("competencias_materia_pd_porcentajes", ("criterio",)),
        (
            "competencias_materia_variables",
            ("criterio", "descriptor"),
        ),
        (
            "competencias_evaluacion_notas",
            ("grupo", "alumno", "criterio"),
        ),
        (
            "competencias_evaluacion_nota_acta",
            ("grupo", "alumno"),
        ),
    )
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT materia_key
                FROM {TABLE}
                WHERE etapa = %s
                """,
                (etapa,),
            )
            db_keys = [str(r["materia_key"] or "").strip() for r in cur.fetchall()]
            keys_to_fix: set[str] = set()
            for canonical, curso_ok in BACH_COMPETENCIAS_CURSO_OVERRIDES.items():
                keys_to_fix.add(canonical)
                for db_key in db_keys:
                    fam = competencias_materia_group_key(db_key) or db_key
                    if fam == canonical:
                        keys_to_fix.add(db_key)
            for materia_key in keys_to_fix:
                canonical = competencias_materia_group_key(materia_key) or materia_key
                curso_ok = BACH_COMPETENCIAS_CURSO_OVERRIDES.get(canonical)
                if curso_ok is None:
                    continue
                for curso_mal in (1, 2):
                    if curso_mal == curso_ok:
                        continue
                    for table, tail_cols in tables:
                        if tail_cols:
                            join = " AND ".join(
                                f"t1.{col} = t2.{col}" for col in tail_cols
                            )
                            cur.execute(
                                f"""
                                DELETE FROM {table} AS t1
                                WHERE t1.etapa = %s
                                  AND t1.curso_asignatura = %s
                                  AND t1.materia_key = %s
                                  AND EXISTS (
                                      SELECT 1 FROM {table} AS t2
                                      WHERE t2.etapa = t1.etapa
                                        AND t2.curso_asignatura = %s
                                        AND t2.materia_key = t1.materia_key
                                        AND {join}
                                  )
                                """,
                                (etapa, curso_mal, materia_key, curso_ok),
                            )
                        cur.execute(
                            f"""
                            UPDATE {table}
                            SET curso_asignatura = %s
                            WHERE etapa = %s
                              AND curso_asignatura = %s
                              AND materia_key = %s
                            """,
                            (curso_ok, etapa, curso_mal, materia_key),
                        )


def _seed_bach_criterios() -> None:
    with get_db() as conn:
        with conn.cursor() as cur:
            # No reescribir el catálogo en cada arranque: miles de round-trips a Neon.
            cur.execute(
                f"SELECT COUNT(*)::int AS n FROM {TABLE} WHERE etapa = 'bach'"
            )
            if int(cur.fetchone()["n"] or 0) > 0:
                return
            for nombre, curso, criterios in SEED_BACH:
                key = competencias_materia_group_key(nombre)
                if not key:
                    continue
                for criterio, descs in criterios:
                    norms = [normalize_descriptor_code(d) for d in descs]
                    cur.execute(
                        f"""
                        INSERT INTO {TABLE} (
                            etapa, curso_asignatura, materia_key, materia_nombre,
                            criterio, competencia_especifica, descriptores
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (etapa, curso_asignatura, materia_key, criterio)
                        DO UPDATE SET
                            materia_nombre = EXCLUDED.materia_nombre,
                            competencia_especifica = EXCLUDED.competencia_especifica,
                            descriptores = EXCLUDED.descriptores
                        """,
                        (
                            "bach",
                            int(curso),
                            key,
                            nombre,
                            criterio,
                            _criterio_ce(criterio),
                            norms,
                        ),
                    )


def _seed_eso_criterios() -> None:
    """Upsert de materias ESO del decreto (fuente de verdad al ir añadiendo anexos)."""
    if not SEED_ESO:
        return
    courses_by_key: dict[str, set[int]] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            for nombre, curso, criterios in SEED_ESO:
                key = competencias_materia_group_key(nombre)
                if not key:
                    continue
                courses_by_key.setdefault(key, set()).add(int(curso))
                codes = [c for c, _d in criterios]
                for criterio, descs in criterios:
                    norms = [normalize_descriptor_code(d) for d in descs]
                    cur.execute(
                        f"""
                        INSERT INTO {TABLE} (
                            etapa, curso_asignatura, materia_key, materia_nombre,
                            criterio, competencia_especifica, descriptores
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (etapa, curso_asignatura, materia_key, criterio)
                        DO UPDATE SET
                            materia_nombre = EXCLUDED.materia_nombre,
                            competencia_especifica = EXCLUDED.competencia_especifica,
                            descriptores = EXCLUDED.descriptores
                        """,
                        (
                            "eso",
                            int(curso),
                            key,
                            nombre,
                            criterio,
                            _criterio_ce(criterio),
                            norms,
                        ),
                    )
                # Quita criterios que ya no están en el decreto para esa materia/curso.
                if codes:
                    cur.execute(
                        f"""
                        DELETE FROM {TABLE}
                        WHERE etapa = 'eso'
                          AND curso_asignatura = %s
                          AND materia_key = %s
                          AND NOT (criterio = ANY(%s))
                        """,
                        (int(curso), key, codes),
                    )
            # Quita cursos antiguos si la materia del decreto cambió de curso.
            for key, cursos_ok in courses_by_key.items():
                cur.execute(
                    f"""
                    DELETE FROM {TABLE}
                    WHERE etapa = 'eso'
                      AND materia_key = %s
                      AND NOT (curso_asignatura = ANY(%s))
                    """,
                    (key, sorted(cursos_ok)),
                )


def list_criterios_materia(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> list[dict[str, Any]]:
    ensure_competencias_materia_criterios_schema()
    raw = (materia_key or "").strip()
    keys: list[str] = []
    for k in (raw, competencias_materia_group_key(raw) or ""):
        if k and k not in keys:
            keys.append(k)
    rows: list[dict[str, Any]] = []
    with get_db() as conn:
        with conn.cursor() as cur:
            for key in keys:
                cur.execute(
                    f"""
                    SELECT
                        etapa,
                        curso_asignatura,
                        materia_key,
                        materia_nombre,
                        criterio,
                        competencia_especifica,
                        descriptores
                    FROM {TABLE}
                    WHERE etapa = %s
                      AND curso_asignatura = %s
                      AND materia_key = %s
                    ORDER BY competencia_especifica, criterio
                    """,
                    (
                        (etapa or "").strip().lower(),
                        int(curso_asignatura),
                        key,
                    ),
                )
                rows = [dict(r) for r in cur.fetchall()]
                if rows:
                    break

    rows.sort(key=lambda r: _sort_criterio(str(r.get("criterio") or "")))
    return rows


def map_criterios_codes() -> dict[tuple[str, int, str], set[str]]:
    """Todos los códigos de criterio, agrupados por (etapa, curso, materia_key)."""
    ensure_competencias_materia_criterios_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT etapa, curso_asignatura, materia_key, criterio
                FROM {TABLE}
                """
            )
            out: dict[tuple[str, int, str], set[str]] = {}
            for r in cur.fetchall():
                etapa = str(r["etapa"] or "").strip().lower()
                key = str(r["materia_key"] or "").strip()
                crit = str(r["criterio"] or "").strip()
                if not etapa or not key or not crit:
                    continue
                try:
                    curso = int(r["curso_asignatura"])
                except (TypeError, ValueError):
                    continue
                out.setdefault((etapa, curso, key), set()).add(crit)
                fam = competencias_materia_group_key(key) or key
                if fam != key:
                    out.setdefault((etapa, curso, fam), set()).add(crit)
            return out


def map_criterios_codes_por_materia(*, etapa: str) -> dict[tuple[int, str], set[str]]:
    ensure_competencias_materia_criterios_schema()
    etapa_v = (etapa or "").strip().lower()
    if not etapa_v:
        return {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT curso_asignatura, materia_key, criterio
                FROM {TABLE}
                WHERE etapa = %s
                """,
                (etapa_v,),
            )
            out: dict[tuple[int, str], set[str]] = {}
            for r in cur.fetchall():
                try:
                    curso = int(r["curso_asignatura"])
                except (TypeError, ValueError):
                    continue
                key = str(r["materia_key"] or "").strip()
                crit = str(r["criterio"] or "").strip()
                if not key or not crit:
                    continue
                out.setdefault((curso, key), set()).add(crit)
            return out


def set_materias_con_criterios(*, etapa: str) -> set[tuple[int, str]]:
    """Pares (curso, materia_key) que ya tienen criterios en la etapa."""
    ensure_competencias_materia_criterios_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT curso_asignatura, materia_key
                FROM {TABLE}
                WHERE etapa = %s
                """,
                ((etapa or "").strip().lower(),),
            )
            out: set[tuple[int, str]] = set()
            for r in cur.fetchall():
                curso = int(r["curso_asignatura"])
                raw_key = str(r["materia_key"] or "")
                out.add((curso, raw_key))
                fam = competencias_materia_group_key(raw_key) or raw_key
                out.add((curso, fam))
            return out


def build_cruces_matrix(criterios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filas para la vista: criterio + dict competencia_clave → sufijos ('1', '1.1', …)."""
    out: list[dict[str, Any]] = []
    for row in criterios:
        by_comp: dict[str, list[str]] = {c: [] for c in COMP_CLAVE_COLS}
        for d in row.get("descriptores") or []:
            code = normalize_descriptor_code(str(d))
            m = re.match(
                r"^(CCL|CP|STEM|CD|CPSAA|CC|CE|CCEC)\s+(\d+(?:\.\d+)?)$",
                code,
                re.IGNORECASE,
            )
            if not m:
                continue
            comp = m.group(1).upper()
            suf = m.group(2)
            if comp in by_comp and suf not in by_comp[comp]:
                by_comp[comp].append(suf)
        for comp in COMP_CLAVE_COLS:
            by_comp[comp].sort(key=lambda s: [int(x) for x in s.split(".")])
        out.append(
            {
                "criterio": row.get("criterio"),
                "competencia_especifica": row.get("competencia_especifica"),
                "por_competencia": by_comp,
                "descriptores": [
                    normalize_descriptor_code(str(d))
                    for d in (row.get("descriptores") or [])
                ],
            }
        )
    return out
