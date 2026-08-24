"""Recálculo de notas por descriptor y competencia (tablas intermedias)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from db.competencias_calculo_config import divisor_pendientes, get_calculo_config
from db.competencias_clave import (
    COMPETENCIAS_CLAVE_SEED,
    descriptores_por_competencia,
)
from db.competencias_materia_criterios import normalize_descriptor_code
from db.connection import get_db
from db.enrolled_subject_catalog import (
    bach_competencias_curso_override,
    competencias_materia_group_key,
    resolve_catalog_stage,
)
from db.enrolled_subjects import CARACTERISTICA_MATERIA_PENDIENTE
from db.groups import list_groups_with_course
from utils.group_stage import stage_of

TABLE_PESOS = "competencias_do_pesos"
TABLE_MATERIA_DO = "competencias_alumno_materia_do"
TABLE_MATERIA_DO_EXTRA = "competencias_alumno_materia_do_extra"
TABLE_DO = "competencias_alumno_descriptor_notas"
TABLE_CC = "competencias_alumno_competencia_notas"

_schema_ready = False
ZERO = Decimal("0")


def _norm_alumno(nombre: str) -> str:
    return " ".join((nombre or "").strip().split()).casefold()


def _etapa_codigo(stage: str | None) -> str | None:
    if stage == "bachillerato":
        return "bach"
    if stage == "eso":
        return "eso"
    return None


def _dec(raw: object) -> Decimal:
    if raw is None:
        return ZERO
    return Decimal(str(raw))


def ensure_competencias_recalc_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_PESOS} (
                    etapa TEXT NOT NULL,
                    curso_asignatura SMALLINT NOT NULL,
                    materia_key TEXT NOT NULL,
                    descriptor TEXT NOT NULL,
                    criterio TEXT NOT NULL,
                    coef0 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    coef1 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    coef2 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    PRIMARY KEY (
                        etapa, curso_asignatura, materia_key, descriptor, criterio
                    )
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_cdp_materia
                ON {TABLE_PESOS} (etapa, curso_asignatura, materia_key)
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_MATERIA_DO} (
                    grupo TEXT NOT NULL,
                    alumno TEXT NOT NULL,
                    etapa TEXT NOT NULL,
                    curso_asignatura SMALLINT NOT NULL,
                    materia_key TEXT NOT NULL,
                    descriptor TEXT NOT NULL,
                    suma_nota_0 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    suma_coef_0 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    suma_nota_1 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    suma_coef_1 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    suma_nota_2 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    suma_coef_2 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (
                        grupo, alumno, etapa, curso_asignatura, materia_key, descriptor
                    )
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_camdo_grupo
                ON {TABLE_MATERIA_DO} (LOWER(TRIM(grupo)))
                """
            )
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_MATERIA_DO_EXTRA} (
                    grupo TEXT NOT NULL,
                    alumno TEXT NOT NULL,
                    etapa TEXT NOT NULL,
                    curso_asignatura SMALLINT NOT NULL,
                    materia_key TEXT NOT NULL,
                    descriptor TEXT NOT NULL,
                    suma_nota_0 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    suma_coef_0 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    suma_nota_1 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    suma_coef_1 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    suma_nota_2 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    suma_coef_2 NUMERIC(16, 10) NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (
                        grupo, alumno, etapa, curso_asignatura, materia_key, descriptor
                    )
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_camdoe_grupo
                ON {TABLE_MATERIA_DO_EXTRA} (LOWER(TRIM(grupo)))
                """
            )
    _schema_ready = True


def refresh_do_pesos_all() -> int:
    """Copia coef0–2 con cruce=1 desde competencias_materia_variables."""
    ensure_competencias_recalc_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE_PESOS}")
            cur.execute(
                f"""
                INSERT INTO {TABLE_PESOS} (
                    etapa, curso_asignatura, materia_key, descriptor, criterio,
                    coef0, coef1, coef2
                )
                SELECT etapa, curso_asignatura, materia_key, descriptor, criterio,
                       COALESCE(coef0, 0), COALESCE(coef1, 0), COALESCE(coef2, 0)
                FROM competencias_materia_variables
                WHERE cruce = 1
                """
            )
            return cur.rowcount or 0


def refresh_do_pesos_materia(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> None:
    ensure_competencias_recalc_schema()
    stage = (etapa or "").strip().lower()
    curso = int(curso_asignatura)
    key = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
    if not stage or not key:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TABLE_PESOS}
                WHERE etapa = %s
                  AND curso_asignatura = %s
                  AND materia_key = %s
                """,
                (stage, curso, key),
            )
            cur.execute(
                f"""
                INSERT INTO {TABLE_PESOS} (
                    etapa, curso_asignatura, materia_key, descriptor, criterio,
                    coef0, coef1, coef2
                )
                SELECT etapa, curso_asignatura, materia_key, descriptor, criterio,
                       COALESCE(coef0, 0), COALESCE(coef1, 0), COALESCE(coef2, 0)
                FROM competencias_materia_variables
                WHERE etapa = %s
                  AND curso_asignatura = %s
                  AND materia_key = %s
                  AND cruce = 1
                """,
                (stage, curso, key),
            )


def _index_pesos(rows: list[dict[str, Any]]) -> dict[tuple[str, int, str], dict[str, list[tuple[str, Decimal, Decimal, Decimal]]]]:
    out: dict[tuple[str, int, str], dict[str, list[tuple[str, Decimal, Decimal, Decimal]]]] = {}
    for r in rows:
        etapa = str(r.get("etapa") or "").strip().lower()
        key = competencias_materia_group_key(str(r.get("materia_key") or "")) or str(
            r.get("materia_key") or ""
        ).strip()
        crit = str(r.get("criterio") or "").strip()
        desc = normalize_descriptor_code(str(r.get("descriptor") or ""))
        try:
            curso = int(r["curso_asignatura"])
        except (TypeError, ValueError):
            continue
        if not etapa or not key or not crit or not desc:
            continue
        bucket = out.setdefault((etapa, curso, key), {})
        bucket.setdefault(desc, []).append(
            (crit, _dec(r.get("coef0")), _dec(r.get("coef1")), _dec(r.get("coef2")))
        )
    return out


def _load_pesos_index() -> dict[tuple[str, int, str], dict[str, list[tuple[str, Decimal, Decimal, Decimal]]]]:
    ensure_competencias_recalc_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT etapa, curso_asignatura, materia_key, descriptor, criterio,
                       coef0, coef1, coef2
                FROM {TABLE_PESOS}
                """
            )
            rows = [dict(r) for r in cur.fetchall()]
    if not rows:
        refresh_do_pesos_all()
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT etapa, curso_asignatura, materia_key, descriptor, criterio,
                           coef0, coef1, coef2
                    FROM {TABLE_PESOS}
                    """
                )
                rows = [dict(r) for r in cur.fetchall()]
    return _index_pesos(rows)


def _ingest_notas_rows(
    rows,
    out: dict[tuple[str, str, str, int, str, str], Decimal],
) -> None:
    for r in rows:
        etapa = str(r["etapa"] or "").strip().lower()
        key = competencias_materia_group_key(str(r["materia_key"] or "")) or str(
            r["materia_key"] or ""
        ).strip()
        al = _norm_alumno(str(r["alumno"] or ""))
        crit = str(r["criterio"] or "").strip()
        grupo_cf = str(r["grupo"] or "").strip().casefold()
        if not etapa or not key or not al or not crit or not grupo_cf:
            continue
        try:
            curso = int(r["curso_asignatura"])
        except (TypeError, ValueError):
            continue
        out[(grupo_cf, al, etapa, curso, key, crit)] = Decimal(str(r["nota"]))


def _load_notas_from_table(
    table: str,
    *,
    grupo: str | None = None,
) -> dict[tuple[str, str, str, int, str, str], Decimal]:
    from db.competencias_evaluacion import ensure_competencias_evaluacion_schema

    ensure_competencias_evaluacion_schema()
    out: dict[tuple[str, str, str, int, str, str], Decimal] = {}
    nombre = (grupo or "").strip()
    with get_db() as conn:
        with conn.cursor() as cur:
            if nombre:
                cur.execute(
                    f"""
                    SELECT etapa, curso_asignatura, materia_key, grupo,
                           alumno, criterio, nota
                    FROM {table}
                    WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                      AND nota IS NOT NULL
                    """,
                    (nombre,),
                )
            else:
                cur.execute(
                    f"""
                    SELECT etapa, curso_asignatura, materia_key, grupo,
                           alumno, criterio, nota
                    FROM {table}
                    WHERE nota IS NOT NULL
                    """
                )
            _ingest_notas_rows(cur.fetchall(), out)
    return out


def _load_ordinary_notas_index(
    *,
    grupo: str | None = None,
) -> dict[tuple[str, str, str, int, str, str], Decimal]:
    from db.competencias_evaluacion import TABLE

    return _load_notas_from_table(TABLE, grupo=grupo)


def _load_extra_notas_index(
    *,
    grupo: str | None = None,
) -> dict[tuple[str, str, str, int, str, str], Decimal]:
    from db.competencias_evaluacion import TABLE_EXTRA

    return _load_notas_from_table(TABLE_EXTRA, grupo=grupo)


def _snapshots_por_grupo_cf(
    *,
    grupo: str | None = None,
) -> dict[str, dict]:
    from db.competencias_bach_ordinaria import (
        mapa_snapshot_ordinaria,
        mapa_snapshots_todos,
        tiene_snapshot_ordinaria,
    )

    nombre = (grupo or "").strip()
    if nombre:
        if not tiene_snapshot_ordinaria(nombre):
            return {}
        return {nombre.casefold(): mapa_snapshot_ordinaria(nombre)}
    return mapa_snapshots_todos()


def _merge_notas_ordinary_extra(
    ordinary: dict[tuple[str, str, str, int, str, str], Decimal],
    extra: dict[tuple[str, str, str, int, str, str], Decimal],
    snaps: dict[str, dict],
) -> dict[tuple[str, str, str, int, str, str], Decimal]:
    """Solo para recálculo de extraordinaria: aprobadas=ordinaria, resto=extra."""
    from db.competencias_bach_ordinaria import (
        aprobado_en_ordinaria,
        nota_snapshot_ordinaria,
    )

    if not snaps and not extra:
        return ordinary

    decision: dict[tuple[str, str, str, int, str], bool | None] = {}

    def _usa_ordinaria(
        grupo_cf: str, al: str, etapa: str, curso: int, mk: str
    ) -> bool | None:
        """True=ordinaria, False=extra, None=sin snapshot (queda ordinaria)."""
        key = (grupo_cf, al, etapa, curso, mk)
        if key in decision:
            return decision[key]
        snap = snaps.get(grupo_cf)
        if not snap or etapa != "bach":
            decision[key] = None
            return None
        nota_ord = nota_snapshot_ordinaria(
            snap,
            etapa=etapa,
            curso=curso,
            materia_key=mk,
            al_norm=al,
        )
        usa = aprobado_en_ordinaria(nota_ord)
        decision[key] = usa
        return usa

    merged: dict[tuple[str, str, str, int, str, str], Decimal] = {}
    for key, val in ordinary.items():
        grupo_cf, al, etapa, curso, mk, _crit = key
        usa = _usa_ordinaria(grupo_cf, al, etapa, curso, mk)
        if usa is False:
            continue
        merged[key] = val

    for key, val in extra.items():
        grupo_cf, al, etapa, curso, mk, _crit = key
        usa = _usa_ordinaria(grupo_cf, al, etapa, curso, mk)
        if usa is True:
            continue
        merged[key] = val

    return merged


def _sesion_es_extraordinaria(sesion: str | None) -> bool:
    return (sesion or "").strip().lower() == "extraordinaria"


def _load_notas_index(
    *,
    grupo: str | None = None,
    sesion: str | None = None,
) -> dict[tuple[str, str, str, int, str, str], Decimal]:
    """Notas de criterio según sesión.

    - ordinaria / ESO: solo tabla ordinaria (nunca se mezclan con extra).
    - extraordinaria: fusiona según snapshot (aprobada→ordinaria, resto→extra).
    """
    ordinary = _load_ordinary_notas_index(grupo=grupo)
    if not _sesion_es_extraordinaria(sesion):
        return ordinary
    extra = _load_extra_notas_index(grupo=grupo)
    if not extra:
        return ordinary
    snaps = _snapshots_por_grupo_cf(grupo=grupo)
    return _merge_notas_ordinary_extra(ordinary, extra, snaps)


def _grupos_etapa_map() -> dict[str, str]:
    """nombre grupo → eso|bach."""
    out: dict[str, str] = {}
    for row in list_groups_with_course():
        nombre = str(row.get("name") or "").strip()
        if not nombre:
            continue
        etapa = _etapa_codigo(stage_of(grupo=nombre, curso=row.get("curso")))
        if etapa:
            out[nombre] = etapa
            out[nombre.casefold()] = etapa
    return out


def _load_matriculas_por_grupo(
    grupo: str | None = None,
) -> dict[str, dict[str, Any]]:
    """grupo → {etapa, alumnos: {norm: canon}, materias: {norm: [(etapa,curso,key), ...]}}."""
    from db.enrolled_subjects import _latest_import_id

    import_id = _latest_import_id()
    grupos_etapa = _grupos_etapa_map()
    if not import_id:
        return {}

    nombre = (grupo or "").strip()
    with get_db() as conn:
        with conn.cursor() as cur:
            if nombre:
                cur.execute(
                    """
                    SELECT DISTINCT
                        TRIM(es.materia) AS materia,
                        TRIM(es.materia_abrev) AS materia_abrev,
                        TRIM(es.alumno) AS alumno,
                        TRIM(es.nombre_grupo) AS nombre_grupo,
                        TRIM(COALESCE(s.grupo, '')) AS student_grupo,
                        c.materia AS catalog_materia,
                        c.curso_asignatura,
                        c.etapa,
                        c.estudio,
                        (TRIM(COALESCE(es.caracteristicas, '')) = %s) AS es_pendiente
                    FROM enrolled_subjects es
                    LEFT JOIN enrolled_subject_catalog c
                      ON TRIM(c.materia_abrev) = TRIM(es.materia_abrev)
                    LEFT JOIN students s
                      ON LOWER(TRIM(s.alumno)) = LOWER(TRIM(es.alumno))
                    WHERE es.import_id = %s
                      AND TRIM(COALESCE(es.materia, '')) <> ''
                      AND (
                        LOWER(TRIM(es.nombre_grupo)) = LOWER(TRIM(%s))
                        OR LOWER(TRIM(COALESCE(s.grupo, ''))) = LOWER(TRIM(%s))
                      )
                    """,
                    (
                        CARACTERISTICA_MATERIA_PENDIENTE,
                        import_id,
                        nombre,
                        nombre,
                    ),
                )
            else:
                cur.execute(
                    """
                    SELECT DISTINCT
                        TRIM(es.materia) AS materia,
                        TRIM(es.materia_abrev) AS materia_abrev,
                        TRIM(es.alumno) AS alumno,
                        TRIM(es.nombre_grupo) AS nombre_grupo,
                        TRIM(COALESCE(s.grupo, '')) AS student_grupo,
                        c.materia AS catalog_materia,
                        c.curso_asignatura,
                        c.etapa,
                        c.estudio,
                        (TRIM(COALESCE(es.caracteristicas, '')) = %s) AS es_pendiente
                    FROM enrolled_subjects es
                    LEFT JOIN enrolled_subject_catalog c
                      ON TRIM(c.materia_abrev) = TRIM(es.materia_abrev)
                    LEFT JOIN students s
                      ON LOWER(TRIM(s.alumno)) = LOWER(TRIM(es.alumno))
                    WHERE es.import_id = %s
                      AND TRIM(COALESCE(es.materia, '')) <> ''
                    """,
                    (CARACTERISTICA_MATERIA_PENDIENTE, import_id),
                )
            filas = [dict(r) for r in cur.fetchall()]

    tmp: dict[str, dict[str, Any]] = {}
    for row in filas:
        grupo = (row.get("student_grupo") or row.get("nombre_grupo") or "").strip()
        if not grupo:
            continue
        etapa_g = grupos_etapa.get(grupo) or grupos_etapa.get(grupo.casefold())
        if not etapa_g:
            continue
        materia = (row.get("catalog_materia") or row.get("materia") or "").strip()
        if not materia:
            continue
        key = competencias_materia_group_key(materia) or materia.casefold()
        try:
            curso = (
                int(row["curso_asignatura"])
                if row.get("curso_asignatura") is not None
                else None
            )
        except (TypeError, ValueError):
            curso = None
        etapa_m = resolve_catalog_stage(
            etapa=row.get("etapa"),
            estudio=row.get("estudio"),
            materia_abrev=row.get("materia_abrev"),
            materia=materia,
        )
        if etapa_m == "bach":
            override = bach_competencias_curso_override(key)
            if override is not None:
                curso = override
        if etapa_m != etapa_g or curso is None:
            continue
        al_raw = str(row.get("alumno") or "").strip()
        al_norm = _norm_alumno(al_raw)
        if not al_norm:
            continue
        g = tmp.setdefault(
            grupo,
            {
                "etapa": etapa_g,
                "alumnos": {},
                "actuales": {},
                "pendientes": {},
            },
        )
        g["alumnos"][al_norm] = al_raw
        dest = "pendientes" if row.get("es_pendiente") else "actuales"
        g[dest].setdefault(al_norm, set()).add((etapa_m, int(curso), key))

    out: dict[str, dict[str, Any]] = {}
    for grupo, data in tmp.items():
        materias: dict[str, list[tuple[str, int, str, bool]]] = {}
        for al_norm, canon in data["alumnos"].items():
            actuales = data["actuales"].get(al_norm) or set()
            pendientes = {
                t
                for t in (data["pendientes"].get(al_norm) or set())
                if (t[2], t[1]) not in {(x[2], x[1]) for x in actuales}
            }
            materias[al_norm] = [(e, c, k, False) for e, c, k in actuales] + [
                (e, c, k, True) for e, c, k in pendientes
            ]
        out[grupo] = {
            "etapa": data["etapa"],
            "alumnos": data["alumnos"],
            "materias": materias,
        }
    return out


def _snapshot_ordinaria_grupo(grupo: str, etapa: str) -> dict:
    if (etapa or "").strip().lower() != "bach":
        return {}
    from db.competencias_bach_ordinaria import mapa_snapshot_ordinaria

    nombre = (grupo or "").strip()
    if not nombre:
        return {}
    return mapa_snapshot_ordinaria(nombre)


def _aportaciones(
    *,
    grupo: str,
    etapa: str,
    alumnos: dict[str, str],
    materias: dict[str, list[tuple[str, int, str, bool]]],
    pesos: dict[tuple[str, int, str], dict[str, list[tuple[str, Decimal, Decimal, Decimal]]]],
    notas: dict[tuple[str, str, str, int, str, str], Decimal],
    divisor_pend: int = 4,
    snapshot_ordinaria: dict | None = None,
    pesos_sesion_cache: dict | None = None,
) -> list[tuple[Any, ...]]:
    from db.competencias_bach_ordinaria import (
        aprobado_en_ordinaria,
        nota_snapshot_ordinaria,
    )
    from db.competencias_materia_variables import pesos_do_materia_sesion
    from db.competencias_pd_porcentajes import get_mismos_pesos_extra

    rows: list[tuple[Any, ...]] = []
    grupo_cf = grupo.casefold()
    div = Decimal(str(max(1, int(divisor_pend))))
    snap = snapshot_ordinaria or {}
    pcache = pesos_sesion_cache if pesos_sesion_cache is not None else {}
    mismos_extra_cache: dict[tuple[str, int, str], bool] = {}
    es_bach = (etapa or "").strip().lower() == "bach"
    for al_norm, alumno in alumnos.items():
        for etapa_m, curso_m, key_m, es_pendiente in materias.get(al_norm) or []:
            factor = (Decimal("1") / div) if es_pendiente else Decimal("1")
            if es_bach and snap:
                nota_ord = nota_snapshot_ordinaria(
                    snap,
                    etapa=etapa_m,
                    curso=curso_m,
                    materia_key=key_m,
                    al_norm=al_norm,
                )
                if aprobado_en_ordinaria(nota_ord):
                    por_desc = pesos.get((etapa_m, curso_m, key_m)) or {}
                else:
                    mk = (etapa_m, curso_m, key_m)
                    if mk not in mismos_extra_cache:
                        mismos_extra_cache[mk] = get_mismos_pesos_extra(
                            etapa=etapa_m,
                            curso_asignatura=curso_m,
                            materia_key=key_m,
                        )
                    if mismos_extra_cache[mk]:
                        por_desc = pesos.get(mk) or {}
                    else:
                        pk = (etapa_m, curso_m, key_m, "extraordinaria")
                        if pk not in pcache:
                            pcache[pk] = pesos_do_materia_sesion(
                                etapa=etapa_m,
                                curso_asignatura=curso_m,
                                materia_key=key_m,
                                sesion="extraordinaria",
                            )
                        por_desc = pcache[pk]
            else:
                por_desc = pesos.get((etapa_m, curso_m, key_m)) or {}
            for desc, pares in por_desc.items():
                sn0 = sc0 = sn1 = sc1 = sn2 = sc2 = ZERO
                for crit, c0, c1, c2 in pares:
                    c0s, c1s, c2s = c0 * factor, c1 * factor, c2 * factor
                    sc0 += c0s
                    sc1 += c1s
                    sc2 += c2s
                    nota = notas.get((grupo_cf, al_norm, etapa_m, curso_m, key_m, crit))
                    if nota is None:
                        continue
                    sn0 += nota * c0s
                    sn1 += nota * c1s
                    sn2 += nota * c2s
                if sc0 == 0 and sc1 == 0 and sc2 == 0 and sn0 == 0 and sn1 == 0 and sn2 == 0:
                    continue
                rows.append(
                    (
                        grupo,
                        alumno,
                        etapa,
                        curso_m,
                        key_m,
                        desc,
                        sn0,
                        sc0,
                        sn1,
                        sc1,
                        sn2,
                        sc2,
                    )
                )
    return rows


def _agregar_descriptores(
    grupo: str,
    etapa: str,
    alumnos: dict[str, str],
    aport: list[tuple[Any, ...]],
) -> list[tuple[Any, ...]]:
    acc: dict[tuple[str, str], list[Decimal]] = {}
    for row in aport:
        alumno = row[1]
        desc = row[5]
        key = (_norm_alumno(alumno), desc)
        bucket = acc.get(key)
        if bucket is None:
            bucket = [ZERO, ZERO, ZERO, ZERO, ZERO, ZERO]
            acc[key] = bucket
        bucket[0] += row[6]
        bucket[1] += row[7]
        bucket[2] += row[8]
        bucket[3] += row[9]
        bucket[4] += row[10]
        bucket[5] += row[11]

    def nd(sn: Decimal, sc: Decimal) -> Decimal | None:
        return None if sc == 0 else sn / sc

    canon = {_norm_alumno(n): n for n in alumnos.values()}
    rows: list[tuple[Any, ...]] = []
    for (al_norm, desc), b in acc.items():
        alumno = alumnos.get(al_norm) or canon.get(al_norm) or al_norm
        rows.append(
            (
                grupo,
                alumno,
                etapa,
                desc,
                b[0],
                b[1],
                nd(b[0], b[1]),
                b[2],
                b[3],
                nd(b[2], b[3]),
                b[4],
                b[5],
                nd(b[4], b[5]),
            )
        )
    return rows


def _agregar_competencias(
    grupo: str,
    etapa: str,
    filas_do: list[tuple[Any, ...]],
) -> list[tuple[Any, ...]]:
    por_comp = descriptores_por_competencia(etapa)
    desc_to_cc: dict[str, str] = {}
    for abrev, descs in por_comp.items():
        for d in descs:
            desc_to_cc[normalize_descriptor_code(d)] = abrev

    by_al_cc: dict[tuple[str, str], dict[str, Any]] = {}
    for row in filas_do:
        alumno = row[1]
        desc = normalize_descriptor_code(str(row[3] or ""))
        abrev = desc_to_cc.get(desc)
        if not abrev:
            continue
        key = (alumno, abrev)
        rec = by_al_cc.get(key)
        if rec is None:
            rec = {
                "sn": [ZERO, ZERO, ZERO],
                "sc": [ZERO, ZERO, ZERO],
                "do": [[], [], []],
            }
            by_al_cc[key] = rec
        rec["sn"][0] += _dec(row[4])
        rec["sc"][0] += _dec(row[5])
        rec["sn"][1] += _dec(row[7])
        rec["sc"][1] += _dec(row[8])
        rec["sn"][2] += _dec(row[10])
        rec["sc"][2] += _dec(row[11])
        for i, idx in enumerate((6, 9, 12)):
            if row[idx] is not None:
                rec["do"][i].append(_dec(row[idx]))

    def cociente(sn: Decimal, sc: Decimal) -> Decimal | None:
        return None if sc == 0 else sn / sc

    def promedio(vals: list[Decimal]) -> Decimal | None:
        if not vals:
            return None
        return sum(vals, ZERO) / Decimal(len(vals))

    seen_al: set[str] = {row[1] for row in filas_do}
    rows: list[tuple[Any, ...]] = []
    alumnos = sorted(seen_al)
    for alumno in alumnos:
        for item in COMPETENCIAS_CLAVE_SEED:
            abrev = item["abreviatura"]
            rec = by_al_cc.get((alumno, abrev))
            if rec is None:
                rows.append(
                    (grupo, alumno, etapa, abrev, None, None, None, None, None, None)
                )
                continue
            rows.append(
                (
                    grupo,
                    alumno,
                    etapa,
                    abrev,
                    cociente(rec["sn"][0], rec["sc"][0]),
                    cociente(rec["sn"][1], rec["sc"][1]),
                    cociente(rec["sn"][2], rec["sc"][2]),
                    promedio(rec["do"][0]),
                    promedio(rec["do"][1]),
                    promedio(rec["do"][2]),
                )
            )
    return rows


def pesos_materias_por_competencia_grupo(
    grupo: str,
    *,
    etapa: str,
    sesion: str | None = None,
    nivel: int | None = None,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    """Peso relativo de cada materia en cada CC (suma_coef_i).

    Devuelve alumno_norm → abreviatura_CC → lista ordenada por peso desc:
    ``{materia_key, curso, materia, suma_coef, pct}``.
    """
    from db.competencias_alumno_descriptor import _norm_alumno
    from db.competencias_calculo_config import nivel_coef_desde_peso

    ensure_competencias_recalc_schema()
    grupo_v = (grupo or "").strip()
    etapa_v = (etapa or "").strip().lower()
    if not grupo_v or not etapa_v:
        return {}

    if nivel is None:
        nivel = nivel_coef_desde_peso(get_calculo_config().get("peso_periodos"))
    nivel = int(nivel)
    if nivel not in (0, 1, 2):
        nivel = 0
    col_coef = f"suma_coef_{nivel}"

    por_comp = descriptores_por_competencia(etapa_v)
    desc_to_cc: dict[str, str] = {}
    for abrev, descs in por_comp.items():
        for d in descs:
            desc_to_cc[normalize_descriptor_code(d)] = abrev

    tbl_md, _tbl_do, _tbl_cc = _result_tables(sesion)
    # alumno_norm → cc → (materia_key, curso) → Decimal
    acc: dict[str, dict[str, dict[tuple[str, int], Decimal]]] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT alumno, curso_asignatura, materia_key, descriptor, {col_coef}
                FROM {tbl_md}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                  AND etapa = %s
                """,
                (grupo_v, etapa_v),
            )
            for r in cur.fetchall():
                al = _norm_alumno(str(r.get("alumno") or ""))
                desc = normalize_descriptor_code(str(r.get("descriptor") or ""))
                abrev = desc_to_cc.get(desc)
                mk = str(r.get("materia_key") or "").strip()
                if not al or not abrev or not mk:
                    continue
                try:
                    curso = int(r.get("curso_asignatura") or 0)
                except (TypeError, ValueError):
                    curso = 0
                coef = _dec(r.get(col_coef))
                if coef == 0:
                    continue
                by_cc = acc.setdefault(al, {})
                by_mat = by_cc.setdefault(abrev, {})
                key = (mk, curso)
                by_mat[key] = by_mat.get(key, ZERO) + coef

    from db.enrolled_subject_catalog import bach_competencias_canonical_label

    cursos_needed = {
        curso
        for by_cc in acc.values()
        for by_mat in by_cc.values()
        for (_mk, curso) in by_mat
    }
    catalog_by_curso: dict[int, list[str]] = {c: [] for c in cursos_needed}
    if cursos_needed:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT curso_asignatura, materia
                    FROM enrolled_subject_catalog
                    WHERE curso_asignatura = ANY(%s)
                    """,
                    (list(cursos_needed),),
                )
                for r in cur.fetchall():
                    try:
                        cu = int(r.get("curso_asignatura") or 0)
                    except (TypeError, ValueError):
                        continue
                    mat = (r.get("materia") or "").strip()
                    if mat and cu in catalog_by_curso:
                        catalog_by_curso[cu].append(mat)

    label_cache: dict[tuple[int, str], str] = {}

    def _label(mk: str, curso: int) -> str:
        ck = (curso, mk)
        if ck in label_cache:
            return label_cache[ck]
        best = ""
        for mat in catalog_by_curso.get(curso) or []:
            rk = competencias_materia_group_key(mat) or mat.casefold()
            if rk == mk and len(mat) > len(best):
                best = mat
        if etapa_v == "bach":
            lab = bach_competencias_canonical_label(mk, curso, best) or best or mk
        else:
            lab = best or mk
        label_cache[ck] = lab
        return lab

    out: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for al, by_cc in acc.items():
        out_al: dict[str, list[dict[str, Any]]] = {}
        for abrev, by_mat in by_cc.items():
            total = sum(by_mat.values(), ZERO)
            filas: list[dict[str, Any]] = []
            for (mk, curso), coef in by_mat.items():
                pct = (coef / total * Decimal("100")) if total > 0 else ZERO
                filas.append(
                    {
                        "materia_key": mk,
                        "curso": curso,
                        "materia": _label(mk, curso),
                        "suma_coef": coef,
                        "pct": pct,
                        "pct_display": _format_pct_es(pct),
                    }
                )
            filas.sort(
                key=lambda x: (-x["pct"], normalize_for_sort_safe(x["materia"]))
            )
            out_al[abrev] = filas
        out[al] = out_al
    return out


def _format_pct_es(value: Decimal) -> str:
    from decimal import ROUND_HALF_UP

    d = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    text = format(d, "f").rstrip("0").rstrip(".")
    return text.replace(".", ",") + " %"


def normalize_for_sort_safe(text: str) -> str:
    try:
        from utils.text import normalize_for_sort

        return normalize_for_sort(text)
    except Exception:
        return (text or "").casefold()


def _result_tables(sesion: str | None) -> tuple[str, str, str]:
    """Tablas materia_do / descriptor / competencia según sesión."""
    from db.competencias_alumno_competencia import table_competencia
    from db.competencias_alumno_descriptor import table_descriptor

    if _sesion_es_extraordinaria(sesion):
        return TABLE_MATERIA_DO_EXTRA, table_descriptor(sesion), table_competencia(sesion)
    return TABLE_MATERIA_DO, table_descriptor(None), table_competencia(None)


def _replace_grupo_tables(
    *,
    grupo: str,
    materia_do: list[tuple[Any, ...]],
    descriptores: list[tuple[Any, ...]],
    competencias: list[tuple[Any, ...]],
    sesion: str | None = None,
) -> None:
    ensure_competencias_recalc_schema()
    from db.competencias_alumno_competencia import ensure_competencias_alumno_competencia_schema
    from db.competencias_alumno_descriptor import ensure_competencias_alumno_descriptor_schema

    ensure_competencias_alumno_descriptor_schema()
    ensure_competencias_alumno_competencia_schema()
    tbl_md, tbl_do, tbl_cc = _result_tables(sesion)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {tbl_md} WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))",
                (grupo,),
            )
            cur.execute(
                f"DELETE FROM {tbl_do} WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))",
                (grupo,),
            )
            cur.execute(
                f"DELETE FROM {tbl_cc} WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))",
                (grupo,),
            )
            if materia_do:
                cur.executemany(
                    f"""
                    INSERT INTO {tbl_md} (
                        grupo, alumno, etapa, curso_asignatura, materia_key, descriptor,
                        suma_nota_0, suma_coef_0, suma_nota_1, suma_coef_1,
                        suma_nota_2, suma_coef_2, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    materia_do,
                )
            if descriptores:
                cur.executemany(
                    f"""
                    INSERT INTO {tbl_do} (
                        grupo, alumno, etapa, descriptor,
                        suma_nota_0, suma_coef_0, nota_do_0,
                        suma_nota_1, suma_coef_1, nota_do_1,
                        suma_nota_2, suma_coef_2, nota_do_2,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    descriptores,
                )
            if competencias:
                cur.executemany(
                    f"""
                    INSERT INTO {tbl_cc} (
                        grupo, alumno, etapa, competencia,
                        nota_cc_0, nota_cc_1, nota_cc_2,
                        nota_cc_prom_0, nota_cc_prom_1, nota_cc_prom_2,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    competencias,
                )


def rebuild_grupo(
    grupo: str,
    *,
    pesos: dict | None = None,
    notas: dict | None = None,
    matriculas: dict | None = None,
    refresh_nota_comp: bool = False,
    sesion: str | None = None,
) -> int:
    """Recalcula aportaciones, descriptores y competencias de un grupo.

    ``sesion=extraordinaria``: fusiona notas (aprobadas ordinaria + resto extra)
    y escribe en tablas ``*_extra``. Ordinaria/ESO solo usa notas ordinarias
    y tablas ordinarias.

    ``refresh_nota_comp`` solo cuando cambian PPDs/pesos o en recálculo global;
    al guardar calificaciones la nota_comp ya se persiste aparte.
    """
    grupo_v = (grupo or "").strip()
    if not grupo_v:
        return 0
    es_extra = _sesion_es_extraordinaria(sesion)
    pesos_i = pesos if pesos is not None else _load_pesos_index()
    notas_i = (
        notas
        if notas is not None
        else _load_notas_index(grupo=grupo_v, sesion=sesion)
    )
    mats = (
        matriculas
        if matriculas is not None
        else _load_matriculas_por_grupo(grupo_v)
    )
    data = mats.get(grupo_v)
    if not data:
        for gname, payload in mats.items():
            if gname.casefold() == grupo_v.casefold():
                data = payload
                grupo_v = gname
                break
    if not data:
        _replace_grupo_tables(
            grupo=grupo_v,
            materia_do=[],
            descriptores=[],
            competencias=[],
            sesion=sesion,
        )
        return 0
    etapa = data["etapa"]
    if es_extra and etapa != "bach":
        return 0
    div_pend = divisor_pendientes(
        get_calculo_config().get("tratamiento_pendientes")
    )
    # Snapshot solo en extraordinaria (para pesos/notas de materias suspensas).
    snap = _snapshot_ordinaria_grupo(grupo_v, etapa) if es_extra else {}
    pcache: dict = {}
    aport = _aportaciones(
        grupo=grupo_v,
        etapa=etapa,
        alumnos=data["alumnos"],
        materias=data["materias"],
        pesos=pesos_i,
        notas=notas_i,
        divisor_pend=div_pend,
        snapshot_ordinaria=snap,
        pesos_sesion_cache=pcache,
    )
    dos = _agregar_descriptores(grupo_v, etapa, data["alumnos"], aport)
    ccs = _agregar_competencias(grupo_v, etapa, dos)
    _replace_grupo_tables(
        grupo=grupo_v,
        materia_do=aport,
        descriptores=dos,
        competencias=ccs,
        sesion=sesion,
    )
    if refresh_nota_comp:
        from db.competencias_evaluacion import refresh_notas_comp_grupo

        refresh_notas_comp_grupo(grupo_v)
    return len(dos)


def _write_all_groups(
    bloques: list[tuple[str, list, list, list]],
) -> int:
    ensure_competencias_recalc_schema()
    from db.competencias_alumno_competencia import ensure_competencias_alumno_competencia_schema
    from db.competencias_alumno_descriptor import ensure_competencias_alumno_descriptor_schema

    ensure_competencias_alumno_descriptor_schema()
    ensure_competencias_alumno_competencia_schema()
    total = 0
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE_MATERIA_DO}")
            cur.execute(f"DELETE FROM {TABLE_DO}")
            cur.execute(f"DELETE FROM {TABLE_CC}")
            all_md: list[tuple[Any, ...]] = []
            all_do: list[tuple[Any, ...]] = []
            all_cc: list[tuple[Any, ...]] = []
            for _grupo, materia_do, descriptores, competencias in bloques:
                all_md.extend(materia_do)
                all_do.extend(descriptores)
                all_cc.extend(competencias)
                total += len(descriptores)
            if all_md:
                cur.executemany(
                    f"""
                    INSERT INTO {TABLE_MATERIA_DO} (
                        grupo, alumno, etapa, curso_asignatura, materia_key, descriptor,
                        suma_nota_0, suma_coef_0, suma_nota_1, suma_coef_1,
                        suma_nota_2, suma_coef_2, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    all_md,
                )
            if all_do:
                cur.executemany(
                    f"""
                    INSERT INTO {TABLE_DO} (
                        grupo, alumno, etapa, descriptor,
                        suma_nota_0, suma_coef_0, nota_do_0,
                        suma_nota_1, suma_coef_1, nota_do_1,
                        suma_nota_2, suma_coef_2, nota_do_2,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    all_do,
                )
            if all_cc:
                cur.executemany(
                    f"""
                    INSERT INTO {TABLE_CC} (
                        grupo, alumno, etapa, competencia,
                        nota_cc_0, nota_cc_1, nota_cc_2,
                        nota_cc_prom_0, nota_cc_prom_1, nota_cc_prom_2,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    """,
                    all_cc,
                )
    return total


def sync_all_grupos() -> int:
    """Recalcula ESO y Bach: ordinaria siempre; extraordinaria solo Bach."""
    refresh_do_pesos_all()
    pesos = _load_pesos_index()
    matriculas = _load_matriculas_por_grupo()
    total = 0
    for grupo, data in matriculas.items():
        total += rebuild_grupo(
            grupo,
            pesos=pesos,
            matriculas=matriculas,
            refresh_nota_comp=True,
            sesion=None,
        )
        if data.get("etapa") == "bach":
            total += rebuild_grupo(
                grupo,
                pesos=pesos,
                matriculas=matriculas,
                refresh_nota_comp=False,
                sesion="extraordinaria",
            )
    return total


def grupos_con_materia(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
    matriculas: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    target = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
    curso = int(curso_asignatura)
    etapa_v = (etapa or "").strip().lower()
    mats = matriculas if matriculas is not None else _load_matriculas_por_grupo()
    found: list[str] = []
    for grupo, data in mats.items():
        if data["etapa"] != etapa_v:
            continue
        hit = False
        for triples in data["materias"].values():
            if any(t[0] == etapa_v and t[1] == curso and t[2] == target for t in triples):
                hit = True
                break
        if hit:
            found.append(grupo)
    return found
