"""Catálogo de materias para evaluación de competencias."""

from __future__ import annotations

import re
from typing import Any

from db.enrolled_subject_catalog import (
    CATALOG_COURSE_NUMS,
    bach_competencias_canonical_label,
    bach_competencias_curso_override,
    coerce_horas_semanales,
    competencias_materia_group_key,
    ensure_subject_catalog_schema,
    fetch_catalog_horas_index,
    is_bach_religion_materia_key,
    list_catalog_for_export,
    map_departamento_desde_matriculas,
    persist_missing_horas_for_abrevs_bulk,
    resolve_catalog_stage,
    sync_missing_catalog_horas,
)

ETAPA_ESO = "eso"
ETAPA_BACH = "bach"
ETAPAS_COMPETENCIAS = frozenset({ETAPA_ESO, ETAPA_BACH})

ETAPA_LABELS = {
    ETAPA_ESO: "ESO",
    ETAPA_BACH: "Bachillerato",
}

_HAS_ROMAN_SUFFIX_RE = re.compile(r"\s+(I{1,3})\s*$", re.IGNORECASE)


def _prefer_materia_label(current: str, candidate: str) -> str:
    """Prefiere etiqueta de catálogo específica y, si no, numeral romano (Griego I)."""
    cur = (current or "").strip()
    cand = (candidate or "").strip()
    if not cur:
        return cand
    if not cand:
        return cur
    # Preferir «…: Francés» solo si el numeral de curso no contradice (se corrige luego).
    if ":" in cand and ":" not in cur:
        return cand
    if ":" in cur and ":" not in cand:
        return cur
    cur_roman = bool(_HAS_ROMAN_SUFFIX_RE.search(cur))
    cand_roman = bool(_HAS_ROMAN_SUFFIX_RE.search(cand))
    if cand_roman and not cur_roman:
        return cand
    if cur_roman and not cand_roman:
        return cur
    if len(cand) > len(cur):
        return cand
    return cur


def _merge_bach_seed_materias(
    grouped: dict[tuple[int, str], dict[str, Any]],
) -> None:
    """Añade / renombra materias Bach de la semilla ausentes en el catálogo.

    Así aparecen p. ej. «Griego I» aunque Neon solo tenga «Griego» o no la tenga.
    """
    from db.competencias_criterios_seeds_bach import SEED_BACH

    seed_labels: dict[tuple[int, str], str] = {}
    for nombre, curso, _criterios in SEED_BACH:
        key = competencias_materia_group_key(nombre)
        if not key:
            continue
        gkey = (int(curso), key)
        seed_labels[gkey] = _prefer_materia_label(seed_labels.get(gkey, ""), nombre)

    for gkey, label in seed_labels.items():
        curso, key_name = gkey
        existing = grouped.get(gkey)
        if existing is None:
            grouped[gkey] = {
                "materia": label,
                "materia_key": key_name,
                "curso_asignatura": curso,
                "etapa": ETAPA_BACH,
                "materia_abrevs": [],
                "departamento": None,
                "horas": None,
            }
            continue
        existing["materia"] = _prefer_materia_label(existing["materia"], label)


def _relocate_bach_grouped_materias(
    grouped: dict[tuple[int, str], dict[str, Any]],
) -> None:
    """Mueve materias al curso canónico y fusiona duplicados (p. ej. Historia Música 1º→2º)."""
    for curso, key in list(grouped.keys()):
        curso_ok = bach_competencias_curso_override(key)
        if curso_ok is None or curso == curso_ok:
            continue
        row = grouped.pop((curso, key))
        row["curso_asignatura"] = curso_ok
        dest = (curso_ok, key)
        existing = grouped.get(dest)
        if existing is None:
            grouped[dest] = row
            continue
        existing["materia"] = _prefer_materia_label(existing["materia"], row["materia"])
        for abrev in row.get("materia_abrevs") or []:
            if abrev and abrev not in (existing.get("materia_abrevs") or []):
                existing.setdefault("materia_abrevs", []).append(abrev)
        if row.get("departamento") and not (existing.get("departamento") or "").strip():
            existing["departamento"] = row["departamento"]
        if row.get("horas") is not None and existing.get("horas") is None:
            existing["horas"] = row["horas"]


def _departamento_lookup(deps: list[dict]) -> dict[str, str]:
    """Nombre o abreviatura (minúsculas) → nombre canónico del departamento."""
    out: dict[str, str] = {}
    for d in deps:
        nombre = (d.get("departamento") or "").strip()
        if not nombre:
            continue
        out[nombre.casefold()] = nombre
        abrev = (d.get("abreviatura") or "").strip()
        if abrev:
            out[abrev.casefold()] = nombre
    return out


def _canonical_departamento_label(
    ref: str | None, lookup: dict[str, str]
) -> str | None:
    raw = (ref or "").strip()
    if not raw:
        return None
    return lookup.get(raw.casefold(), raw)


def _infer_departamento_from_nombre(
    materia: str | None,
    materia_key: str | None,
    departamentos: list[dict],
) -> str | None:
    """Si el nombre de materia encaja con un departamento del catálogo."""
    from utils.text import normalize_for_sort

    mat_key = normalize_for_sort(materia_key or "")
    mat_name = normalize_for_sort(materia or "")
    if not mat_key and not mat_name:
        return None
    best: tuple[int, str] | None = None
    for d in departamentos:
        nombre = (d.get("departamento") or "").strip()
        abrev = (d.get("abreviatura") or "").strip()
        nkey = normalize_for_sort(nombre)
        akey = normalize_for_sort(abrev)
        if not nkey and not akey:
            continue
        hit = False
        score = 0
        if nkey and (mat_key.startswith(nkey) or nkey in mat_key or mat_name.startswith(nkey)):
            hit = True
            score = len(nkey)
        if akey and (mat_key == akey or mat_name == akey):
            hit = True
            score = max(score, len(akey) + 10)
        if hit and nombre:
            if best is None or score > best[0]:
                best = (score, nombre)
    return best[1] if best else None


_HORAS_FUZZY_MIN = 8


def _lookup_horas_catalogo(
    *,
    curso: int,
    key: str,
    abrevs: list[str] | None,
    by_group: dict[tuple[int, str], int],
    by_abrev: dict[str, int],
    by_key: dict[str, int],
) -> int | None:
    """Horas del catálogo: mismo curso, abreviatura, misma materia u homónimo."""
    if key:
        found = by_group.get((curso, key))
        if found is not None:
            return found
    for abr in abrevs or []:
        found = by_abrev.get((abr or "").strip().lower())
        if found is not None:
            return found
    if key:
        found = by_key.get(key)
        if found is not None:
            return found
        best_h: int | None = None
        best = 0
        for ck, horas_n in by_key.items():
            score = 0
            if ck == key:
                return horas_n
            if ck in key and len(ck) >= _HORAS_FUZZY_MIN:
                score = len(ck)
            elif key in ck and len(key) >= _HORAS_FUZZY_MIN:
                score = len(key)
            if score > best:
                best = score
                best_h = horas_n
        if best_h is not None:
            return best_h
    return None


def _enrich_horas(
    grouped: dict[tuple[int, str], dict[str, Any]], *, stage: str
) -> None:
    """Rellena horas vacías desde el catálogo Neon o, si falta, el horario CyL."""
    from db.competencias_horas_cyl import horas_curriculares

    by_group, by_abrev, by_key = fetch_catalog_horas_index(stage)
    pending: list[tuple[list[str], int]] = []
    for row in grouped.values():
        found = coerce_horas_semanales(row.get("horas"))
        if found is None:
            found = _lookup_horas_catalogo(
                curso=int(row["curso_asignatura"]),
                key=row.get("materia_key") or "",
                abrevs=row.get("materia_abrevs") or [],
                by_group=by_group,
                by_abrev=by_abrev,
                by_key=by_key,
            )
        if found is None:
            found = horas_curriculares(
                etapa=stage,
                curso=int(row["curso_asignatura"]),
                materia_key=row.get("materia_key") or "",
            )
        if found is None:
            continue
        row["horas"] = found
        pending.append((row.get("materia_abrevs") or [], found))
    persist_missing_horas_for_abrevs_bulk(pending)


def _merge_eso_seed_materias(
    grouped: dict[tuple[int, str], dict[str, Any]],
) -> None:
    """Añade materias ESO de la semilla (p. ej. ámbitos DC) ausentes en Neon."""
    from db.competencias_criterios_seeds_eso import SEED_ESO

    seed_labels: dict[tuple[int, str], str] = {}
    for nombre, curso, _criterios in SEED_ESO:
        key = competencias_materia_group_key(nombre)
        if not key:
            continue
        gkey = (int(curso), key)
        seed_labels[gkey] = _prefer_materia_label(seed_labels.get(gkey, ""), nombre)

    for gkey, label in seed_labels.items():
        curso, key_name = gkey
        existing = grouped.get(gkey)
        if existing is None:
            grouped[gkey] = {
                "materia": label,
                "materia_key": key_name,
                "curso_asignatura": curso,
                "etapa": ETAPA_ESO,
                "materia_abrevs": [],
                "departamento": None,
                "horas": None,
            }
            continue
        existing["materia"] = _prefer_materia_label(existing["materia"], label)


def _enrich_departamentos(grouped: dict[tuple[int, str], dict[str, Any]]) -> None:
    """Rellena departamento vacío: catálogo → matrículas → nombre vs departamentos."""
    from db.departamentos import list_departamentos

    deps = list_departamentos()
    lookup = _departamento_lookup(deps)
    need = [r for r in grouped.values() if not (r.get("departamento") or "").strip()]
    by_abrev: dict[str, str] = {}
    if need:
        by_abrev = map_departamento_desde_matriculas()
    for row in grouped.values():
        current = (row.get("departamento") or "").strip()
        if not current:
            for abr in row.get("materia_abrevs") or []:
                found = by_abrev.get((abr or "").strip().lower())
                if found:
                    current = found
                    break
        if not current:
            current = (
                _infer_departamento_from_nombre(
                    row.get("materia"),
                    row.get("materia_key"),
                    deps,
                )
                or ""
            )
        row["departamento"] = _canonical_departamento_label(current, lookup)


def list_materias_por_etapa(etapa: str) -> list[dict[str, Any]]:
    """Materias del catálogo Neon para ESO o Bachillerato.

    Una fila por (curso, nombre de materia): unifica modalidades
    (p. ej. Economía BCT y BHS → una sola «Economía»).
    ``materia_abrevs`` guarda todas las abreviaturas agrupadas para
    que las acciones futuras afecten a todas por igual.
    En Bachillerato se completan con la semilla curricular (p. ej. Griego I).
    """
    stage = (etapa or "").strip().lower()
    if stage not in ETAPAS_COMPETENCIAS:
        return []

    ensure_subject_catalog_schema()
    sync_missing_catalog_horas(etapa=stage)
    allowed = set(CATALOG_COURSE_NUMS.get(stage, ()))
    grouped: dict[tuple[int, str], dict[str, Any]] = {}

    for row in list_catalog_for_export():
        resolved = resolve_catalog_stage(
            etapa=row.get("etapa"),
            estudio=row.get("estudio"),
            materia_abrev=row.get("materia_abrev"),
            materia=row.get("materia"),
        )
        if resolved != stage:
            continue
        try:
            curso = int(row.get("curso_asignatura") or 0)
        except (TypeError, ValueError):
            continue
        if curso not in allowed:
            continue

        materia = (row.get("materia") or "").strip()
        key_name = competencias_materia_group_key(materia)
        if not key_name:
            continue
        curso_override = (
            bach_competencias_curso_override(key_name) if stage == ETAPA_BACH else None
        )
        if curso_override is not None:
            curso = curso_override
        # En Bach 2º no hay Religión (cualquier confesión).
        if (
            stage == ETAPA_BACH
            and curso == 2
            and is_bach_religion_materia_key(key_name)
        ):
            continue

        abrev = (row.get("materia_abrev") or "").strip()
        departamento = (row.get("departamento") or "").strip() or None
        horas_n = coerce_horas_semanales(row.get("horas"), row.get("phoras"))
        gkey = (curso, key_name)
        existing = grouped.get(gkey)
        if existing is None:
            grouped[gkey] = {
                "materia": materia,
                "materia_key": key_name,
                "curso_asignatura": curso,
                "etapa": stage,
                "materia_abrevs": [abrev] if abrev else [],
                "departamento": departamento,
                "horas": horas_n,
            }
            continue

        if abrev and abrev not in existing["materia_abrevs"]:
            existing["materia_abrevs"].append(abrev)
        existing["materia"] = _prefer_materia_label(existing["materia"], materia)
        if departamento and not (existing.get("departamento") or "").strip():
            existing["departamento"] = departamento
        if horas_n is not None and existing.get("horas") is None:
            existing["horas"] = horas_n

    if stage == ETAPA_BACH:
        _merge_bach_seed_materias(grouped)
        _relocate_bach_grouped_materias(grouped)
        for gkey in list(grouped.keys()):
            curso_g, key_g = gkey
            if curso_g == 2 and is_bach_religion_materia_key(key_g):
                del grouped[gkey]
        for row in grouped.values():
            row["materia"] = bach_competencias_canonical_label(
                row["materia_key"],
                int(row["curso_asignatura"]),
                row.get("materia"),
            )
    elif stage == ETAPA_ESO:
        _merge_eso_seed_materias(grouped)

    _enrich_horas(grouped, stage=stage)
    _enrich_departamentos(grouped)

    out = list(grouped.values())
    out.sort(
        key=lambda r: (
            int(r["curso_asignatura"]),
            (r["materia"] or "").lower(),
        )
    )
    return out


def get_materia_por_clave(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> dict[str, Any] | None:
    """Localiza una materia agrupada del listado por etapa/curso/clave."""
    key = (materia_key or "").strip()
    curso = int(curso_asignatura)
    for m in list_materias_por_etapa(etapa):
        if int(m["curso_asignatura"]) == curso and m["materia_key"] == key:
            return m
    return None


def materias_con_flag_criterios(etapa: str) -> list[dict[str, Any]]:
    """Listado de materias indicando si ya tienen criterios / porcentajes PD."""
    from db.competencias_materia_criterios import set_materias_con_criterios
    from db.competencias_pd_porcentajes import set_materias_con_porcentajes_pd

    loaded = set_materias_con_criterios(etapa=etapa)
    loaded_pd = set_materias_con_porcentajes_pd(etapa=etapa)
    out = []
    for m in list_materias_por_etapa(etapa):
        row = dict(m)
        key = (int(m["curso_asignatura"]), m["materia_key"])
        row["tiene_criterios"] = key in loaded
        row["tiene_porcentajes_pd"] = key in loaded_pd
        out.append(row)
    return out
