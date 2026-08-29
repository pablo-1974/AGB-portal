"""Notas por descriptor operativo y alumno (suma_nota_*, suma_coef_*, nota_do_*)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from db.competencias_clave import list_descriptores_operativos
from db.competencias_materia_criterios import normalize_descriptor_code
from db.connection import get_db
from db.enrolled_subject_catalog import competencias_materia_group_key
from db.groups import ensure_groups_schema, get_group_curso, list_groups_with_course
from utils.group_stage import stage_of
from utils.text import normalize_for_sort

TABLE = "competencias_alumno_descriptor_notas"
TABLE_EXTRA = "competencias_alumno_descriptor_notas_extra"

_schema_ready = False


def _sesion_es_extraordinaria(sesion: str | None) -> bool:
    return (sesion or "").strip().lower() == "extraordinaria"


def table_descriptor(sesion: str | None = None) -> str:
    return TABLE_EXTRA if _sesion_es_extraordinaria(sesion) else TABLE

_COEF_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("coef0", "suma_nota_0", "suma_coef_0", "nota_do_0"),
    ("coef1", "suma_nota_1", "suma_coef_1", "nota_do_1"),
    ("coef2", "suma_nota_2", "suma_coef_2", "nota_do_2"),
)


def _norm_alumno(nombre: str) -> str:
    from utils.text import normalize_alumno_key

    return normalize_alumno_key(nombre)


def _etapa_grupo(grupo: str) -> str | None:
    """eso | bach según el código del grupo."""
    curso = get_group_curso(grupo)
    stage = stage_of(grupo=grupo, curso=curso)
    if stage == "bachillerato":
        return "bach"
    if stage == "eso":
        return "eso"
    return None


def _nota_do(suma_nota: Decimal, suma_coef: Decimal) -> Decimal | None:
    if suma_coef == 0:
        return None
    return suma_nota / suma_coef


def ensure_competencias_alumno_descriptor_schema() -> None:
    """Crea la tabla si no existe. No recalcula filas al arrancar."""
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            for tbl, idx_g, idx_e in (
                (TABLE, "idx_cadn_grupo", "idx_cadn_etapa"),
                (TABLE_EXTRA, "idx_cadne_grupo", "idx_cadne_etapa"),
            ):
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {tbl} (
                        grupo TEXT NOT NULL,
                        alumno TEXT NOT NULL,
                        etapa TEXT NOT NULL,
                        descriptor TEXT NOT NULL,
                        suma_nota_0 NUMERIC(16, 10),
                        suma_coef_0 NUMERIC(16, 10),
                        nota_do_0 NUMERIC(16, 10),
                        suma_nota_1 NUMERIC(16, 10),
                        suma_coef_1 NUMERIC(16, 10),
                        nota_do_1 NUMERIC(16, 10),
                        suma_nota_2 NUMERIC(16, 10),
                        suma_coef_2 NUMERIC(16, 10),
                        nota_do_2 NUMERIC(16, 10),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (grupo, alumno, descriptor)
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {idx_g}
                    ON {tbl} (LOWER(TRIM(grupo)))
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {idx_e}
                    ON {tbl} (etapa)
                    """
                )
    _schema_ready = True


def list_grupos_etapa(etapa: str) -> list[str]:
    """Grupos de la etapa (eso | bach)."""
    etapa_v = (etapa or "").strip().lower()
    ensure_groups_schema()
    out: list[str] = []
    for row in list_groups_with_course():
        nombre = str(row.get("name") or "").strip()
        if not nombre:
            continue
        resolved = _etapa_grupo(nombre)
        if resolved == etapa_v:
            out.append(nombre)
    out.sort(key=normalize_for_sort)
    return out


def list_grupos_con_materia(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> list[str]:
    """Grupos con alumnos matriculados en la materia (última importación)."""
    from competencias.evaluar_grupos import _agrupar_materias_filas, _filas_materias_grupo
    from db.enrolled_subjects import _latest_import_id

    etapa_v = (etapa or "").strip().lower()
    curso = int(curso_asignatura)
    target = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
    if not etapa_v or not target:
        return []

    import_id = _latest_import_id()
    if not import_id:
        return []

    found: list[str] = []
    for grupo in list_grupos_etapa(etapa_v):
        filas = _filas_materias_grupo(nombre=grupo, import_id=import_id)
        for m in _agrupar_materias_filas(filas):
            if (m.get("etapa") or "").strip().lower() != etapa_v:
                continue
            try:
                c = int(m["curso_asignatura"])
            except (TypeError, ValueError):
                continue
            if c != curso:
                continue
            mk = (m.get("materia_key") or "").strip()
            if mk == target or (competencias_materia_group_key(mk) or mk) == target:
                found.append(grupo)
                break
    return found


def _triple_key(m: dict[str, Any]) -> tuple[str, int, str] | None:
    etapa = (m.get("etapa") or "").strip().lower()
    key = (m.get("materia_key") or "").strip()
    try:
        curso = int(m["curso_asignatura"])
    except (TypeError, ValueError):
        return None
    if not etapa or not key:
        return None
    fam = competencias_materia_group_key(key) or key
    return (etapa, curso, fam)


def _load_variables_materias(
    materias: set[tuple[str, int, str]],
) -> dict[tuple[str, int, str], list[dict[str, Any]]]:
    if not materias:
        return {}
    from db.competencias_materia_variables import ensure_competencias_materia_variables_schema

    ensure_competencias_materia_variables_schema()
    out: dict[tuple[str, int, str], list[dict[str, Any]]] = {k: [] for k in materias}
    with get_db() as conn:
        with conn.cursor() as cur:
            for etapa, curso, key in materias:
                keys = [key]
                raw = key
                for k in (raw, competencias_materia_group_key(raw) or ""):
                    if k and k not in keys:
                        keys.append(k)
                for mk in keys:
                    cur.execute(
                        """
                        SELECT criterio, descriptor, cruce,
                               coef0, coef1, coef2
                        FROM competencias_materia_variables
                        WHERE etapa = %s
                          AND curso_asignatura = %s
                          AND materia_key = %s
                        """,
                        (etapa, curso, mk),
                    )
                    rows = cur.fetchall()
                    if rows:
                        out[(etapa, curso, key)] = [dict(r) for r in rows]
                        break
    return out


def _load_notas_grupo(grupo: str) -> dict[tuple[str, int, str, str, str], Decimal]:
    """(alumno_norm, etapa, curso, materia_key, criterio) → nota."""
    from db.competencias_evaluacion import ensure_competencias_evaluacion_schema

    ensure_competencias_evaluacion_schema()
    out: dict[tuple[str, int, str, str, str], Decimal] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT etapa, curso_asignatura, materia_key,
                       alumno, criterio, nota
                FROM competencias_evaluacion_notas
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                  AND nota IS NOT NULL
                """,
                ((grupo or "").strip(),),
            )
            for r in cur.fetchall():
                etapa = str(r["etapa"] or "").strip().lower()
                key = str(r["materia_key"] or "").strip()
                al = _norm_alumno(str(r["alumno"] or ""))
                crit = str(r["criterio"] or "").strip()
                if not etapa or not key or not al or not crit:
                    continue
                try:
                    curso = int(r["curso_asignatura"])
                except (TypeError, ValueError):
                    continue
                fam = competencias_materia_group_key(key) or key
                out[(al, etapa, curso, fam, crit)] = Decimal(str(r["nota"]))
    return out


def _materias_alumnos_grupo(
    grupo: str,
    etapa: str,
) -> tuple[dict[str, str], dict[str, list[tuple[str, int, str]]], set[tuple[str, int, str]]]:
    """Alumno canónico, materias por alumno_norm, conjunto de triples materia."""
    from competencias.evaluar_grupos import _agrupar_materias_filas, _filas_materias_grupo
    from db.enrolled_subjects import _latest_import_id

    import_id = _latest_import_id()
    if not import_id:
        return {}, {}, set()

    agrupadas = _agrupar_materias_filas(
        _filas_materias_grupo(nombre=grupo, import_id=import_id)
    )
    actuales: list[dict[str, Any]] = []
    pendientes: list[dict[str, Any]] = []
    actuales_keys: set[tuple[Any, Any]] = set()
    for m in agrupadas:
        if m.get("es_pendiente"):
            pendientes.append(m)
        else:
            actuales.append(m)
            actuales_keys.add((m.get("materia_key"), m.get("curso_asignatura")))
    pendientes = [
        m
        for m in pendientes
        if (m.get("materia_key"), m.get("curso_asignatura")) not in actuales_keys
    ]
    materias = actuales + pendientes

    alumnos_canon: dict[str, str] = {}
    por_alumno: dict[str, list[tuple[str, int, str]]] = {}
    triples: set[tuple[str, int, str]] = set()

    for m in materias:
        if (m.get("etapa") or "").strip().lower() != etapa:
            continue
        tkey = _triple_key(m)
        if not tkey:
            continue
        triples.add(tkey)
        for al_norm in m.get("alumnos") or set():
            if not al_norm:
                continue
            if al_norm not in alumnos_canon:
                alumnos_canon[al_norm] = al_norm
            por_alumno.setdefault(al_norm, [])
            if tkey not in por_alumno[al_norm]:
                por_alumno[al_norm].append(tkey)

    return alumnos_canon, por_alumno, triples


def _calcular_filas_grupo(
    *,
    grupo: str,
    etapa: str,
) -> list[tuple[Any, ...]]:
    from db.students import get_students_by_group

    alumnos_canon, por_alumno, triples = _materias_alumnos_grupo(grupo, etapa)
    for s in get_students_by_group(grupo):
        nombre = str(s.get("alumno") if isinstance(s, dict) else s or "").strip()
        if not nombre:
            continue
        alumnos_canon.setdefault(_norm_alumno(nombre), nombre)
    if not alumnos_canon:
        return []

    variables = _load_variables_materias(triples)
    notas = _load_notas_grupo(grupo)
    descriptores = list_descriptores_operativos(etapa)

    rows: list[tuple[Any, ...]] = []
    for al_norm, alumno in sorted(alumnos_canon.items(), key=lambda x: x[1].lower()):
        materias_al = por_alumno.get(al_norm) or []
        for desc in descriptores:
            desc_norm = normalize_descriptor_code(desc)
            sumas: dict[str, Decimal] = {
                "suma_nota_0": Decimal("0"),
                "suma_coef_0": Decimal("0"),
                "suma_nota_1": Decimal("0"),
                "suma_coef_1": Decimal("0"),
                "suma_nota_2": Decimal("0"),
                "suma_coef_2": Decimal("0"),
            }
            for etapa_m, curso_m, key_m in materias_al:
                for var in variables.get((etapa_m, curso_m, key_m)) or []:
                    crit = str(var.get("criterio") or "").strip()
                    var_desc = normalize_descriptor_code(str(var.get("descriptor") or ""))
                    if not crit or var_desc != desc_norm:
                        continue
                    cruce = int(var.get("cruce") or 0)
                    coefs = {
                        "coef0": Decimal(str(var["coef0"]))
                        if var.get("coef0") is not None
                        else Decimal("0"),
                        "coef1": Decimal(str(var["coef1"]))
                        if var.get("coef1") is not None
                        else Decimal("0"),
                        "coef2": Decimal(str(var["coef2"]))
                        if var.get("coef2") is not None
                        else Decimal("0"),
                    }
                    nota = notas.get((al_norm, etapa_m, curso_m, key_m, crit))
                    for coef_key, sn_key, sc_key, _nd_key in _COEF_FIELDS:
                        coef = coefs[coef_key]
                        sumas[sc_key] += Decimal(int(cruce)) * coef
                        if nota is not None:
                            sumas[sn_key] += nota * coef

            notas_do = {
                "nota_do_0": _nota_do(sumas["suma_nota_0"], sumas["suma_coef_0"]),
                "nota_do_1": _nota_do(sumas["suma_nota_1"], sumas["suma_coef_1"]),
                "nota_do_2": _nota_do(sumas["suma_nota_2"], sumas["suma_coef_2"]),
            }
            rows.append(
                (
                    grupo,
                    alumno,
                    etapa,
                    desc,
                    sumas["suma_nota_0"],
                    sumas["suma_coef_0"],
                    notas_do["nota_do_0"],
                    sumas["suma_nota_1"],
                    sumas["suma_coef_1"],
                    notas_do["nota_do_1"],
                    sumas["suma_nota_2"],
                    sumas["suma_coef_2"],
                    notas_do["nota_do_2"],
                )
            )
    return rows


def rebuild_alumno_descriptor_grupo(
    grupo: str,
    *,
    refresh_nota_comp: bool = False,
    sesion: str | None = None,
) -> int:
    """Recalcula suma_nota/suma_coef/nota_do y competencias de un grupo."""
    from db.competencias_recalc import rebuild_grupo

    return rebuild_grupo(
        grupo, refresh_nota_comp=refresh_nota_comp, sesion=sesion
    )


def rebuild_alumno_descriptor_etapa(etapa: str) -> int:
    """Recalcula todos los grupos de la etapa."""
    from db.competencias_recalc import (
        _load_matriculas_por_grupo,
        _load_pesos_index,
        rebuild_grupo,
    )

    etapa_v = (etapa or "").strip().lower()
    pesos = _load_pesos_index()
    matriculas = _load_matriculas_por_grupo()
    total = 0
    for grupo, data in matriculas.items():
        if data.get("etapa") != etapa_v:
            continue
        total += rebuild_grupo(
            grupo,
            pesos=pesos,
            matriculas=matriculas,
            refresh_nota_comp=True,
            sesion=None,
        )
        if etapa_v == "bach":
            total += rebuild_grupo(
                grupo,
                pesos=pesos,
                matriculas=matriculas,
                refresh_nota_comp=False,
                sesion="extraordinaria",
            )
    return total


def rebuild_alumno_descriptor_materia(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> int:
    """Recalcula grupos con alumnos matriculados en la materia."""
    from db.competencias_recalc import (
        _load_matriculas_por_grupo,
        _load_pesos_index,
        grupos_con_materia,
        rebuild_grupo,
    )

    etapa_v = (etapa or "").strip().lower()
    pesos = _load_pesos_index()
    matriculas = _load_matriculas_por_grupo()
    total = 0
    seen: set[str] = set()
    for grupo in grupos_con_materia(
        etapa=etapa,
        curso_asignatura=curso_asignatura,
        materia_key=materia_key,
        matriculas=matriculas,
    ):
        g = grupo.strip()
        if not g or g in seen:
            continue
        seen.add(g)
        total += rebuild_grupo(
            g,
            pesos=pesos,
            matriculas=matriculas,
            refresh_nota_comp=True,
            sesion=None,
        )
        if etapa_v == "bach":
            total += rebuild_grupo(
                g,
                pesos=pesos,
                matriculas=matriculas,
                refresh_nota_comp=False,
                sesion="extraordinaria",
            )
    return total


def sync_all_alumno_descriptor_notas() -> int:
    """Recalcula ESO y Bachillerato (p. ej. calculadora de Evaluaciones)."""
    from db.competencias_recalc import sync_all_grupos

    return sync_all_grupos()


def format_nota_do_es(value: Decimal | None) -> str:
    """Nota descriptor en pantalla (hasta 2 decimales, coma decimal)."""
    if value is None:
        return ""
    from decimal import ROUND_HALF_UP

    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = format(d, "f").rstrip("0").rstrip(".")
    return text.replace(".", ",")


def filas_descriptor_por_alumno_grupo(
    grupo: str,
    *,
    etapa: str,
    sesion: str | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Mapa alumno_norm → filas {descriptor, nota_do_0, nota_do_1, nota_do_2}."""
    ensure_competencias_alumno_descriptor_schema()
    etapa_v = (etapa or "").strip().lower()
    grupo_v = (grupo or "").strip()
    if not etapa_v or not grupo_v:
        return {}
    tbl = table_descriptor(sesion)

    by_alumno: dict[str, dict[str, dict[str, Decimal | None]]] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT alumno, descriptor,
                       nota_do_0, nota_do_1, nota_do_2
                FROM {tbl}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                  AND etapa = %s
                ORDER BY alumno, descriptor
                """,
                (grupo_v, etapa_v),
            )
            for r in cur.fetchall():
                al = _norm_alumno(str(r["alumno"] or ""))
                desc = normalize_descriptor_code(str(r["descriptor"] or ""))
                if not al or not desc:
                    continue
                by_alumno.setdefault(al, {})[desc] = {
                    "nota_do_0": (
                        Decimal(str(r["nota_do_0"]))
                        if r.get("nota_do_0") is not None
                        else None
                    ),
                    "nota_do_1": (
                        Decimal(str(r["nota_do_1"]))
                        if r.get("nota_do_1") is not None
                        else None
                    ),
                    "nota_do_2": (
                        Decimal(str(r["nota_do_2"]))
                        if r.get("nota_do_2") is not None
                        else None
                    ),
                }

    descriptores = list_descriptores_operativos(etapa_v)
    out: dict[str, list[dict[str, str]]] = {}
    alumnos = set(by_alumno.keys())
    for al in alumnos:
        desc_map = by_alumno.get(al, {})
        filas: list[dict[str, str]] = []
        for desc in descriptores:
            desc_norm = normalize_descriptor_code(desc)
            vals = desc_map.get(desc_norm) or {}
            filas.append(
                {
                    "descriptor": desc,
                    "nota_do_0": format_nota_do_es(vals.get("nota_do_0")),
                    "nota_do_1": format_nota_do_es(vals.get("nota_do_1")),
                    "nota_do_2": format_nota_do_es(vals.get("nota_do_2")),
                }
            )
        out[al] = filas
    return out


def map_nota_do_grupo(
    grupo: str,
    *,
    nivel: int = 0,
) -> dict[tuple[str, str], Decimal]:
    """Mapa (alumno_norm, descriptor_norm) → nota_do_N del grupo."""
    ensure_competencias_alumno_descriptor_schema()
    col = f"nota_do_{int(nivel)}"
    if col not in ("nota_do_0", "nota_do_1", "nota_do_2"):
        return {}
    out: dict[tuple[str, str], Decimal] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT alumno, descriptor, {col}
                FROM {TABLE}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                  AND {col} IS NOT NULL
                """,
                ((grupo or "").strip(),),
            )
            for r in cur.fetchall():
                al = _norm_alumno(str(r["alumno"] or ""))
                desc = normalize_descriptor_code(str(r["descriptor"] or ""))
                if not al or not desc:
                    continue
                out[(al, desc)] = Decimal(str(r[col]))
    return out
