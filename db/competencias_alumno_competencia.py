"""Notas de las 8 competencias clave por alumno (nota_cc_* y nota_cc_prom_*)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from db.competencias_alumno_descriptor import (
    TABLE as TABLE_DO,
    _norm_alumno,
    format_nota_do_es,
    ensure_competencias_alumno_descriptor_schema,
)
from db.competencias_calculo_config import (
    PROMEDIO_SI,
    format_nota_cc_2d_es,
    format_nota_cc_entera_es,
    get_calculo_config,
    nivel_coef_desde_peso,
)
from db.competencias_clave import (
    COMPETENCIAS_CLAVE_SEED,
    descriptores_por_competencia,
)
from db.competencias_materia_criterios import normalize_descriptor_code
from db.connection import get_db

TABLE = "competencias_alumno_competencia_notas"
TABLE_EXTRA = "competencias_alumno_competencia_notas_extra"

_schema_ready = False


def _sesion_es_extraordinaria(sesion: str | None) -> bool:
    return (sesion or "").strip().lower() == "extraordinaria"


def table_competencia(sesion: str | None = None) -> str:
    return TABLE_EXTRA if _sesion_es_extraordinaria(sesion) else TABLE


def _avg(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    total = Decimal("0")
    for v in values:
        total += v
    return total / Decimal(len(values))


def _cociente(suma_nota: Decimal, suma_coef: Decimal) -> Decimal | None:
    if suma_coef == 0:
        return None
    return suma_nota / suma_coef


def ensure_competencias_alumno_competencia_schema() -> None:
    """Crea la tabla si no existe. No recalcula filas al arrancar."""
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            for tbl, idx in (
                (TABLE, "idx_cacn_grupo"),
                (TABLE_EXTRA, "idx_cacne_grupo"),
            ):
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {tbl} (
                        grupo TEXT NOT NULL,
                        alumno TEXT NOT NULL,
                        etapa TEXT NOT NULL,
                        competencia TEXT NOT NULL,
                        nota_cc_0 NUMERIC(16, 10),
                        nota_cc_1 NUMERIC(16, 10),
                        nota_cc_2 NUMERIC(16, 10),
                        nota_cc_prom_0 NUMERIC(16, 10),
                        nota_cc_prom_1 NUMERIC(16, 10),
                        nota_cc_prom_2 NUMERIC(16, 10),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (grupo, alumno, competencia)
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {idx}
                    ON {tbl} (LOWER(TRIM(grupo)))
                    """
                )
    _schema_ready = True


def rebuild_alumno_competencia_grupo(grupo: str) -> int:
    """Agrega nota_cc y nota_cc_prom a partir de las filas de descriptores del grupo."""
    ensure_competencias_alumno_descriptor_schema()
    ensure_competencias_alumno_competencia_schema()
    grupo_v = (grupo or "").strip()
    if not grupo_v:
        return 0

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT alumno, etapa, descriptor,
                       suma_nota_0, suma_coef_0, nota_do_0,
                       suma_nota_1, suma_coef_1, nota_do_1,
                       suma_nota_2, suma_coef_2, nota_do_2
                FROM {TABLE_DO}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                """,
                (grupo_v,),
            )
            raw_rows = [dict(r) for r in cur.fetchall()]

    if not raw_rows:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    DELETE FROM {TABLE}
                    WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                    """,
                    (grupo_v,),
                )
        return 0

    etapa = str(raw_rows[0].get("etapa") or "").strip().lower()
    por_comp = descriptores_por_competencia(etapa)
    desc_to_comp: dict[str, str] = {}
    for abrev, descs in por_comp.items():
        for d in descs:
            desc_to_comp[normalize_descriptor_code(d)] = abrev

    by_alumno: dict[str, dict[str, Any]] = {}
    for r in raw_rows:
        al = str(r.get("alumno") or "").strip()
        if not al:
            continue
        bucket = by_alumno.setdefault(al, {"etapa": etapa, "descs": {}})
        desc = normalize_descriptor_code(str(r.get("descriptor") or ""))
        if not desc:
            continue
        bucket["descs"][desc] = r

    rows: list[tuple[Any, ...]] = []
    for alumno, data in by_alumno.items():
        descs_map = data["descs"]
        for item in COMPETENCIAS_CLAVE_SEED:
            abrev = item["abreviatura"]
            codes = por_comp.get(abrev, ())
            sumas_n = [Decimal("0"), Decimal("0"), Decimal("0")]
            sumas_c = [Decimal("0"), Decimal("0"), Decimal("0")]
            dos: list[list[Decimal]] = [[], [], []]
            for code in codes:
                rec = descs_map.get(normalize_descriptor_code(code))
                if not rec:
                    continue
                for i in range(3):
                    sn = rec.get(f"suma_nota_{i}")
                    sc = rec.get(f"suma_coef_{i}")
                    nd = rec.get(f"nota_do_{i}")
                    if sn is not None:
                        sumas_n[i] += Decimal(str(sn))
                    if sc is not None:
                        sumas_c[i] += Decimal(str(sc))
                    if nd is not None:
                        dos[i].append(Decimal(str(nd)))
            rows.append(
                (
                    grupo_v,
                    alumno,
                    etapa,
                    abrev,
                    _cociente(sumas_n[0], sumas_c[0]),
                    _cociente(sumas_n[1], sumas_c[1]),
                    _cociente(sumas_n[2], sumas_c[2]),
                    _avg(dos[0]),
                    _avg(dos[1]),
                    _avg(dos[2]),
                )
            )

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TABLE}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                """,
                (grupo_v,),
            )
            if rows:
                cur.executemany(
                    f"""
                    INSERT INTO {TABLE} (
                        grupo, alumno, etapa, competencia,
                        nota_cc_0, nota_cc_1, nota_cc_2,
                        nota_cc_prom_0, nota_cc_prom_1, nota_cc_prom_2,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        NOW()
                    )
                    """,
                    rows,
                )
    return len(rows)


_CC_COLS = (
    "nota_cc_0",
    "nota_cc_1",
    "nota_cc_2",
    "nota_cc_prom_0",
    "nota_cc_prom_1",
    "nota_cc_prom_2",
)


def _fila_cc_vacia() -> dict[str, str]:
    out = {col: "" for col in _CC_COLS}
    return out


def filas_competencia_por_alumno_grupo(
    grupo: str,
    *,
    sesion: str | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Mapa alumno_norm → 8 competencias con nota activa y las seis variantes."""
    ensure_competencias_alumno_competencia_schema()
    cfg = get_calculo_config()
    nivel = nivel_coef_desde_peso(cfg.get("peso_periodos"))
    usar_prom = cfg.get("promedio_descriptores") == PROMEDIO_SI
    modo_dec = str(cfg.get("decimales") or "")
    col_activa = f"nota_cc_prom_{nivel}" if usar_prom else f"nota_cc_{nivel}"
    tbl = table_competencia(sesion)

    by_alumno: dict[str, dict[str, dict[str, Decimal | None]]] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT alumno, competencia,
                       nota_cc_0, nota_cc_1, nota_cc_2,
                       nota_cc_prom_0, nota_cc_prom_1, nota_cc_prom_2
                FROM {tbl}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                """,
                ((grupo or "").strip(),),
            )
            for r in cur.fetchall():
                al = _norm_alumno(str(r["alumno"] or ""))
                abrev = str(r.get("competencia") or "").strip()
                if not al or not abrev:
                    continue
                by_alumno.setdefault(al, {})[abrev] = {
                    col: (
                        Decimal(str(r[col])) if r.get(col) is not None else None
                    )
                    for col in _CC_COLS
                }

    out: dict[str, list[dict[str, str]]] = {}
    for al, por_comp in by_alumno.items():
        filas: list[dict[str, str]] = []
        for item in COMPETENCIAS_CLAVE_SEED:
            abrev = item["abreviatura"]
            vals = por_comp.get(abrev) or {}
            activa = vals.get(col_activa)
            fila: dict[str, str] = {
                "abreviatura": abrev,
                "nombre": item["nombre"],
                "nota": format_nota_cc_entera_es(activa, modo_dec),
                "nota_2d": format_nota_cc_2d_es(activa),
                "editada_sesion": False,
            }
            for col in _CC_COLS:
                fila[col] = format_nota_do_es(vals.get(col))
            filas.append(fila)
        out[al] = filas
    return out


def competencias_vacias() -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for c in COMPETENCIAS_CLAVE_SEED:
        fila = {
            "abreviatura": c["abreviatura"],
            "nombre": c["nombre"],
            "nota": "",
            "nota_2d": "",
            "editada_sesion": False,
        }
        fila.update(_fila_cc_vacia())
        out.append(fila)
    return out
