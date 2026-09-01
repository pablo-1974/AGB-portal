"""Carga docente por departamento (Reparto)."""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from db.connection import get_db
from db.enrolled_subject_catalog import normalize_catalog_etapa
from utils.text import normalize_for_sort

TABLE = "reparto_carga_docente"
_schema_ready = False

_ETAPA_LABEL = {
    "eso": "ESO",
    "bach": "Bachillerato",
    "fpb": "FPB",
    "fpm": "FPM",
}


def ensure_reparto_carga_docente_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id SERIAL PRIMARY KEY,
                    departamento_abrev TEXT NOT NULL,
                    etapa TEXT,
                    curso_asignatura SMALLINT,
                    materia_abrev TEXT NOT NULL DEFAULT '',
                    materia TEXT NOT NULL DEFAULT '',
                    grupos TEXT NOT NULL DEFAULT '',
                    horas_por_grupo NUMERIC(8, 2),
                    horas_totales NUMERIC(8, 2),
                    tutoria BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_reparto_cd_depto
                ON {TABLE} (departamento_abrev, id)
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS tutoria BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS dc BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS profesores_distintos SMALLINT NOT NULL DEFAULT 1
                """
            )
    _schema_ready = True


def _grupos_int(grupos: str) -> int:
    g = _dec(grupos)
    if g is None:
        return 0
    if g == g.to_integral_value():
        return max(0, int(g))
    return 0


def _profesores_distintos_valido(grupos: str, raw) -> int:
    g = _grupos_int(grupos)
    try:
        d = int(raw)
    except (TypeError, ValueError):
        d = 1
    cap = max(1, g)
    return max(1, min(d, cap))


def _dec(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    raw = str(value).strip().replace(",", ".")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def _fmt(value) -> str:
    d = _dec(value)
    if d is None:
        return ""
    if d == d.to_integral_value():
        return str(int(d))
    return format(d.normalize(), "f").rstrip("0").rstrip(".")


def _totales(grupos: str, horas_por_grupo) -> Decimal | None:
    g = _dec(grupos)
    h = _dec(horas_por_grupo)
    if g is None or h is None:
        return None
    return g * h


def _tutoria_extra(etapa: str | None) -> Decimal:
    et = (etapa or "").strip().lower()
    if et == "eso":
        return Decimal(2)
    if et == "bach":
        return Decimal(1)
    return Decimal(0)


def _horas_por_grupo_efectivas(
    etapa: str | None,
    horas_por_grupo,
    tutoria: bool,
) -> Decimal | None:
    hpg = _dec(horas_por_grupo)
    if hpg is None:
        return None
    if tutoria:
        hpg += _tutoria_extra(etapa)
    return hpg


def _base_horas_por_grupo(
    etapa: str | None,
    horas_efectivas,
    tutoria: bool,
) -> Decimal | None:
    h = _dec(horas_efectivas)
    if h is None:
        return None
    if tutoria:
        h -= _tutoria_extra(etapa)
        if h < 0:
            h = Decimal(0)
    return h


def _resolve_hpg_save(
    *,
    etapa: str | None,
    horas_por_grupo: str,
    tutoria: bool,
    catalogo_horas,
) -> tuple[Decimal | None, Decimal | None]:
    """Devuelve (horas base a guardar, horas efectivas para totales)."""
    manual = str(horas_por_grupo or "").strip()
    if manual:
        eff = _dec(manual)
        base = _base_horas_por_grupo(etapa, eff, tutoria) if tutoria else eff
        return base, eff
    base = _dec(catalogo_horas)
    eff = _horas_por_grupo_efectivas(etapa, base, tutoria)
    return base, eff


def _curso_label(etapa: str | None, curso: int | None) -> str:
    if curso is None:
        return ""
    et = _ETAPA_LABEL.get((etapa or "").strip().lower() or "", "")
    if et:
        return f"{curso}º {et}"
    return f"{curso}º"


def _curso_key(etapa: str | None, curso: int | None) -> str:
    return f"{(etapa or '').strip()}|{curso if curso is not None else ''}"


def _materia_ident(m: dict) -> str:
    return str(m.get("abrev") or m.get("nombre") or "").strip()


def _resolve_materia(catalogo: dict, curso_key: str, materia_abrev: str) -> dict | None:
    mab = (materia_abrev or "").strip()
    if not mab:
        return None
    mats = (catalogo.get("materias_by_curso") or {}).get(curso_key) or []
    mat = next((m for m in mats if _materia_ident(m) == mab), None)
    if mat:
        return mat
    return next((m for m in (catalogo.get("materias") or []) if _materia_ident(m) == mab), None)


def catalogo_carga_departamento(*, nombre: str = "", abreviatura: str = "") -> dict:
    """Cursos y materias del catálogo (todos los departamentos)."""
    _ = (nombre, abreviatura)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT etapa, curso_asignatura, materia_abrev, materia, horas
                FROM enrolled_subject_catalog
                """
            )
            rows = [dict(r) for r in cur.fetchall()]

    materias_by_curso: dict[str, list[dict]] = {}
    cursos_map: dict[str, dict] = {}
    seen_mat: dict[str, set[str]] = {}
    for r in rows:
        etapa = normalize_catalog_etapa(str(r.get("etapa") or "")) or (
            str(r.get("etapa") or "").strip().lower() or None
        )
        try:
            curso = int(r["curso_asignatura"]) if r.get("curso_asignatura") is not None else None
        except (TypeError, ValueError):
            curso = None
        if curso is None:
            continue
        ck = _curso_key(etapa, curso)
        if ck not in cursos_map:
            cursos_map[ck] = {
                "key": ck,
                "label": _curso_label(etapa, curso),
                "etapa": etapa or "",
                "curso": curso,
            }
        abrev = str(r.get("materia_abrev") or "").strip()
        nombre_m = str(r.get("materia") or abrev).strip()
        if not abrev and not nombre_m:
            continue
        ident = abrev or nombre_m
        seen_mat.setdefault(ck, set())
        if ident in seen_mat[ck]:
            continue
        seen_mat[ck].add(ident)
        materias_by_curso.setdefault(ck, []).append(
            {
                "abrev": abrev,
                "nombre": nombre_m,
                "horas": _fmt(r.get("horas")),
            }
        )

    for mats in materias_by_curso.values():
        mats.sort(key=lambda m: normalize_for_sort(m.get("nombre") or m.get("abrev") or ""))

    seen_all: set[str] = set()
    materias: list[dict] = []
    for mats in materias_by_curso.values():
        for m in mats:
            ident = (m.get("abrev") or m.get("nombre") or "").strip()
            if not ident or ident in seen_all:
                continue
            seen_all.add(ident)
            materias.append({"abrev": m.get("abrev") or "", "nombre": m.get("nombre") or ident})
    materias.sort(key=lambda m: normalize_for_sort(m.get("nombre") or m.get("abrev") or ""))

    cursos = sorted(
        cursos_map.values(),
        key=lambda c: (
            str(c.get("etapa") or ""),
            int(c.get("curso") or 0),
        ),
    )
    return {"cursos": cursos, "materias": materias, "materias_by_curso": materias_by_curso}


def catalogo_carga_json(*, nombre: str, abreviatura: str) -> str:
    return json.dumps(
        catalogo_carga_departamento(nombre=nombre, abreviatura=abreviatura),
        ensure_ascii=False,
    )


def list_carga_docente(departamento_abrev: str) -> list[dict]:
    ensure_reparto_carga_docente_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, etapa, curso_asignatura, materia_abrev, materia,
                       grupos, horas_por_grupo, horas_totales, tutoria, dc,
                       profesores_distintos
                FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                ORDER BY id ASC
                """,
                (key,),
            )
            out = []
            for r in cur.fetchall():
                try:
                    curso = int(r["curso_asignatura"]) if r.get("curso_asignatura") is not None else None
                except (TypeError, ValueError):
                    curso = None
                etapa = str(r.get("etapa") or "").strip() or None
                tutoria = bool(r.get("tutoria"))
                hpg_base = r.get("horas_por_grupo")
                hpg_eff = _horas_por_grupo_efectivas(etapa, hpg_base, tutoria)
                ht = _totales(str(r.get("grupos") or ""), hpg_eff)
                out.append(
                    {
                        "id": int(r["id"]),
                        "curso_label": _curso_label(etapa, curso),
                        "materia": str(r.get("materia") or r.get("materia_abrev") or ""),
                        "grupos": str(r.get("grupos") or ""),
                        "horas_por_grupo": _fmt(hpg_eff),
                        "horas_totales": _fmt(ht),
                        "tutoria": tutoria,
                        "dc": bool(r.get("dc")),
                        "curso_key": _curso_key(etapa, curso),
                        "materia_abrev": str(r.get("materia_abrev") or ""),
                        "profesores_distintos": int(
                            r.get("profesores_distintos") or 1
                        ),
                    }
                )
            return out


def add_carga_docente(
    *,
    departamento_abrev: str,
    curso_key: str,
    materia_abrev: str,
    grupos: str,
    tutoria: bool,
    dc: bool,
    catalogo: dict,
    horas_por_grupo: str = "",
    profesores_distintos: int = 1,
) -> bool:
    ensure_reparto_carga_docente_schema()
    key = (departamento_abrev or "").strip()
    ck = (curso_key or "").strip()
    mab = (materia_abrev or "").strip()
    grupos_n = (grupos or "").strip()
    if not key or not ck or not mab:
        return False
    prof_dist = _profesores_distintos_valido(grupos_n, profesores_distintos)
    curso_info = next((c for c in catalogo.get("cursos") or [] if c.get("key") == ck), None)
    mat = _resolve_materia(catalogo, ck, mab)
    if not curso_info or not mat:
        return False
    etapa = (curso_info.get("etapa") or "").strip() or None
    hpg_base, hpg_eff = _resolve_hpg_save(
        etapa=etapa,
        horas_por_grupo=horas_por_grupo,
        tutoria=bool(tutoria),
        catalogo_horas=mat.get("horas"),
    )
    ht = _totales(grupos_n, hpg_eff)
    curso = curso_info.get("curso")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    departamento_abrev, etapa, curso_asignatura,
                    materia_abrev, materia, grupos,
                    horas_por_grupo, horas_totales, tutoria, dc,
                    profesores_distintos
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    key,
                    etapa,
                    int(curso) if curso is not None else None,
                    mat.get("abrev") or mab,
                    mat.get("nombre") or mab,
                    grupos_n,
                    hpg_base,
                    ht,
                    bool(tutoria),
                    bool(dc),
                    prof_dist,
                ),
            )
    return True


def update_carga_docente(
    *,
    fila_id: int,
    departamento_abrev: str,
    curso_key: str,
    materia_abrev: str,
    grupos: str,
    tutoria: bool,
    dc: bool,
    catalogo: dict,
    horas_por_grupo: str = "",
    profesores_distintos: int = 1,
) -> bool:
    ensure_reparto_carga_docente_schema()
    key = (departamento_abrev or "").strip()
    ck = (curso_key or "").strip()
    mab = (materia_abrev or "").strip()
    grupos_n = (grupos or "").strip()
    if not key or not ck or not mab or int(fila_id) <= 0:
        return False
    prof_dist = _profesores_distintos_valido(grupos_n, profesores_distintos)
    curso_info = next((c for c in catalogo.get("cursos") or [] if c.get("key") == ck), None)
    mat = _resolve_materia(catalogo, ck, mab)
    if not curso_info or not mat:
        return False
    etapa = (curso_info.get("etapa") or "").strip() or None
    hpg_base, hpg_eff = _resolve_hpg_save(
        etapa=etapa,
        horas_por_grupo=horas_por_grupo,
        tutoria=bool(tutoria),
        catalogo_horas=mat.get("horas"),
    )
    ht = _totales(grupos_n, hpg_eff)
    curso = curso_info.get("curso")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET etapa = %s,
                    curso_asignatura = %s,
                    materia_abrev = %s,
                    materia = %s,
                    grupos = %s,
                    horas_por_grupo = %s,
                    horas_totales = %s,
                    tutoria = %s,
                    dc = %s,
                    profesores_distintos = %s
                WHERE id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (
                    etapa,
                    int(curso) if curso is not None else None,
                    mat.get("abrev") or mab,
                    mat.get("nombre") or mab,
                    grupos_n,
                    hpg_base,
                    ht,
                    bool(tutoria),
                    bool(dc),
                    prof_dist,
                    int(fila_id),
                    key,
                ),
            )
            return cur.rowcount > 0


def delete_carga_docente(*, fila_id: int, departamento_abrev: str) -> bool:
    ensure_reparto_carga_docente_schema()
    key = (departamento_abrev or "").strip()
    if not key or int(fila_id) <= 0:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TABLE}
                WHERE id = %s
                  AND LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (int(fila_id), key),
            )
            return cur.rowcount > 0
