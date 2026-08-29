"""Variables por cruce descriptor operativo × criterio de evaluación."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from db.competencias_clave import list_descriptores_operativos
from db.competencias_materia_criterios import (
    ensure_competencias_materia_criterios_schema,
    list_criterios_materia,
    normalize_descriptor_code,
)
from db.competencias_pd_porcentajes import (
    ensure_competencias_pd_porcentajes_schema,
    list_porcentajes_materia,
)
from db.connection import get_db
from db.enrolled_subject_catalog import (
    competencias_materia_group_key,
    compute_phoras,
    ensure_subject_catalog_schema,
    resolve_catalog_stage,
)

TABLE = "competencias_materia_variables"

_schema_ready = False
_table_ready = False


def compute_cruce(descriptor: str, descriptores_criterio: list[str] | None) -> int:
    """1 si el descriptor operativo cruza con el criterio; 0 si no."""
    target = normalize_descriptor_code(descriptor)
    if not target:
        return 0
    for d in descriptores_criterio or []:
        if normalize_descriptor_code(str(d)) == target:
            return 1
    return 0


def compute_dototal(
    cruces_ppd: list[tuple[int, Decimal | None]],
) -> Decimal:
    """dototal: suma de (cruce × ppd) sobre los criterios de un descriptor."""
    total = Decimal("0")
    for cruce, ppd in cruces_ppd:
        if not cruce or ppd is None:
            continue
        total += Decimal(int(cruce)) * Decimal(str(ppd))
    return total


def compute_donumcru(cruces: list[int]) -> int:
    """donumcru: nº de criterios de la materia con los que cruza el descriptor."""
    return sum(1 for c in cruces if int(c or 0) == 1)


def compute_coef0(
    *,
    cruce: int,
    ppd: Decimal | None,
    donumcru: int,
    dototal: Decimal | None,
) -> Decimal:
    """coef0 = cruce × ppd × donumcru / dototal."""
    if not cruce or ppd is None or not donumcru:
        return Decimal("0")
    dt = Decimal(str(dototal or 0))
    if dt == 0:
        return Decimal("0")
    return (
        Decimal(int(cruce)) * Decimal(str(ppd)) * Decimal(int(donumcru))
    ) / dt


def compute_coef1(coef0: Decimal, phoras: Decimal | None) -> Decimal | None:
    """coef1 = coef0 × phoras."""
    if phoras is None:
        return None
    return Decimal(str(coef0)) * Decimal(str(phoras))


def compute_sumcoef1(coef1_values: list[Decimal | None]) -> Decimal:
    """sumcoef1: suma de todos los coef1 de la materia."""
    total = Decimal("0")
    for v in coef1_values:
        if v is None:
            continue
        total += Decimal(str(v))
    return total


def compute_coef2(
    coef1: Decimal | None,
    sumcoef1: Decimal | None,
) -> Decimal | None:
    """coef2 = coef1 ÷ sumcoef1."""
    if coef1 is None or sumcoef1 is None:
        return None
    s = Decimal(str(sumcoef1))
    if s == 0:
        return None
    return Decimal(str(coef1)) / s


def phoras_efectiva(phoras: Decimal | None) -> Decimal | None:
    """phoras de cálculo: la del catálogo (horas/30), igual si es pendiente."""
    if phoras is None:
        return None
    return Decimal(str(phoras))


def resolve_phoras_efectiva_materia(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> Decimal | None:
    """phoras del catálogo."""
    return phoras_efectiva(
        _resolve_phoras_materia(
            etapa=etapa,
            curso_asignatura=curso_asignatura,
            materia_key=materia_key,
        )
    )


def contexto_ppd_phoras_materia(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
    sesion: str | None = None,
    pendiente: bool = False,
) -> dict[str, Any]:
    """Porcentajes (ppd) según sesión/pendiente; phoras del catálogo."""
    stage = (etapa or "").strip().lower()
    curso = int(curso_asignatura)
    key = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
    return {
        "ppd_map": list_porcentajes_materia(
            etapa=stage,
            curso_asignatura=curso,
            materia_key=key,
            sesion=sesion,
            pendiente=pendiente,
        ),
        "phoras": resolve_phoras_efectiva_materia(
            etapa=stage,
            curso_asignatura=curso,
            materia_key=key,
        ),
    }


def _resolve_phoras_materia(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> Decimal | None:
    """phoras de la materia (catálogo: horas/30)."""
    ensure_subject_catalog_schema()
    stage = (etapa or "").strip().lower()
    curso = int(curso_asignatura)
    key = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
    if not stage or not key:
        return None
    from db.enrolled_subject_catalog import (
        bach_competencias_curso_override,
        coerce_horas_semanales,
        list_catalog_for_export,
    )

    fallback: Decimal | None = None
    for row in list_catalog_for_export():
        resolved = resolve_catalog_stage(
            etapa=row.get("etapa"),
            estudio=row.get("estudio"),
            materia_abrev=row.get("materia_abrev"),
            materia=row.get("materia"),
        )
        if resolved != stage:
            continue
        row_key = competencias_materia_group_key(row.get("materia"))
        if row_key != key:
            continue
        try:
            row_curso = int(row.get("curso_asignatura") or 0)
        except (TypeError, ValueError):
            continue
        curso_canon = row_curso
        ov = bach_competencias_curso_override(row_key)
        if ov is not None:
            curso_canon = ov
        phoras = row.get("phoras")
        horas_n = coerce_horas_semanales(row.get("horas"), phoras)
        if phoras is not None:
            value: Decimal | None = Decimal(str(phoras))
        else:
            value = compute_phoras(horas_n)
        if value is None:
            continue
        if row_curso == curso or curso_canon == curso:
            return value
        if fallback is None:
            fallback = value
    return fallback


def _ensure_table() -> None:
    global _table_ready
    with get_db() as conn:
        with conn.cursor() as cur:
            if not _table_ready:
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {TABLE} (
                        etapa TEXT NOT NULL,
                        curso_asignatura SMALLINT NOT NULL,
                        materia_key TEXT NOT NULL,
                        criterio TEXT NOT NULL,
                        descriptor TEXT NOT NULL,
                        cruce SMALLINT NOT NULL DEFAULT 0
                            CHECK (cruce IN (0, 1)),
                        ppd NUMERIC(16, 10),
                        dototal NUMERIC(16, 10),
                        donumcru SMALLINT,
                        coef0 NUMERIC(16, 10),
                        coef1 NUMERIC(16, 10),
                        sumcoef1 NUMERIC(16, 10),
                        coef2 NUMERIC(16, 10),
                        phoras NUMERIC(16, 10),
                        PRIMARY KEY (
                            etapa, curso_asignatura, materia_key, criterio, descriptor
                        )
                    )
                    """
                )
                cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS idx_cmv_materia
                    ON {TABLE} (etapa, curso_asignatura, materia_key)
                    """
                )
            for col, typ in (
                ("ppd", "NUMERIC(16, 10)"),
                ("dototal", "NUMERIC(16, 10)"),
                ("donumcru", "SMALLINT"),
                ("coef0", "NUMERIC(16, 10)"),
                ("coef1", "NUMERIC(16, 10)"),
                ("sumcoef1", "NUMERIC(16, 10)"),
                ("coef2", "NUMERIC(16, 10)"),
                ("phoras", "NUMERIC(16, 10)"),
            ):
                cur.execute(
                    f"""
                    ALTER TABLE {TABLE}
                    ADD COLUMN IF NOT EXISTS {col} {typ}
                    """
                )
            # Renombrar columna antigua si existía de un despliegue previo.
            cur.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = %s
                  AND column_name = 'suma_cruce_ppd'
                """,
                (TABLE,),
            )
            if cur.fetchone():
                cur.execute(
                    f"""
                    UPDATE {TABLE}
                    SET dototal = COALESCE(dototal, suma_cruce_ppd)
                    WHERE dototal IS NULL AND suma_cruce_ppd IS NOT NULL
                    """
                )
                cur.execute(
                    f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS suma_cruce_ppd"
                )
    _table_ready = True


def ensure_competencias_materia_variables_schema() -> None:
    """Crea la tabla si no existe. No recalcula filas al arrancar."""
    global _schema_ready
    if _schema_ready:
        return
    ensure_competencias_materia_criterios_schema()
    ensure_competencias_pd_porcentajes_schema()
    ensure_subject_catalog_schema()
    _ensure_table()
    _schema_ready = True


def _calcular_filas_materia_variables(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
    sesion: str | None = None,
    pendiente: bool = False,
) -> tuple[list[tuple[Any, ...]], Decimal | None]:
    """Calcula filas (etapa, curso, key, …) sin escribir en BD."""
    stage = (etapa or "").strip().lower()
    curso = int(curso_asignatura)
    key = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
    if not stage or not key:
        return [], None

    criterios = list_criterios_materia(
        etapa=stage,
        curso_asignatura=curso,
        materia_key=key,
    )
    ctx = contexto_ppd_phoras_materia(
        etapa=stage,
        curso_asignatura=curso,
        materia_key=key,
        sesion=sesion,
        pendiente=pendiente,
    )
    pct_map = ctx["ppd_map"]
    phoras = ctx["phoras"]
    descriptores = [
        normalize_descriptor_code(d) for d in list_descriptores_operativos(stage)
    ]

    por_desc_pares: dict[str, list[tuple[int, Decimal | None]]] = {
        d: [] for d in descriptores
    }
    filas_base: list[tuple[str, str, int, Decimal | None]] = []
    for crit in criterios:
        criterio = str(crit.get("criterio") or "").strip()
        if not criterio:
            continue
        linked = crit.get("descriptores") or []
        ppd: Decimal | None = pct_map.get(criterio)
        for desc in descriptores:
            cruce = compute_cruce(desc, linked)
            por_desc_pares[desc].append((cruce, ppd))
            filas_base.append((criterio, desc, cruce, ppd))

    dototal_por_desc = {
        desc: compute_dototal(pares) for desc, pares in por_desc_pares.items()
    }
    donumcru_por_desc = {
        desc: compute_donumcru([c for c, _ppd in pares])
        for desc, pares in por_desc_pares.items()
    }

    filas_calc: list[
        tuple[str, str, int, Decimal | None, Decimal, int, Decimal, Decimal | None]
    ] = []
    coef1_list: list[Decimal | None] = []
    for criterio, desc, cruce, ppd in filas_base:
        donumcru = donumcru_por_desc[desc]
        dototal = dototal_por_desc[desc]
        coef0 = compute_coef0(
            cruce=cruce,
            ppd=ppd,
            donumcru=donumcru,
            dototal=dototal,
        )
        coef1 = compute_coef1(coef0, phoras)
        coef1_list.append(coef1)
        filas_calc.append(
            (criterio, desc, cruce, ppd, dototal, donumcru, coef0, coef1)
        )

    sumcoef1 = compute_sumcoef1(coef1_list)

    rows: list[tuple[Any, ...]] = [
        (
            stage,
            curso,
            key,
            criterio,
            desc,
            cruce,
            ppd,
            dototal,
            donumcru,
            coef0,
            coef1,
            sumcoef1,
            compute_coef2(coef1, sumcoef1),
            phoras,
        )
        for criterio, desc, cruce, ppd, dototal, donumcru, coef0, coef1 in filas_calc
    ]
    return rows, phoras


def pesos_do_materia_sesion(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
    sesion: str | None = None,
    pendiente: bool = False,
) -> dict[str, list[tuple[str, Decimal, Decimal, Decimal]]]:
    """Mapa descriptor → [(criterio, coef0, coef1, coef2)] solo cruces activos."""
    rows, _ = _calcular_filas_materia_variables(
        etapa=etapa,
        curso_asignatura=curso_asignatura,
        materia_key=materia_key,
        sesion=sesion,
        pendiente=pendiente,
    )
    out: dict[str, list[tuple[str, Decimal, Decimal, Decimal]]] = {}
    for row in rows:
        crit = str(row[3] or "").strip()
        desc = normalize_descriptor_code(str(row[4] or ""))
        if int(row[5] or 0) != 1:
            continue
        if not crit or not desc:
            continue
        coef0 = Decimal(str(row[9]))
        coef1 = Decimal(str(row[10]))
        coef2_v = Decimal(str(row[12]))
        out.setdefault(desc, []).append((crit, coef0, coef1, coef2_v))
    return out


def rebuild_materia_variables(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
    sesion: str | None = None,
    pendiente: bool = False,
) -> int:
    """Recalcula variables de una materia (incl. coef0–coef2, sumcoef1)."""
    ensure_competencias_materia_criterios_schema()
    ensure_competencias_pd_porcentajes_schema()
    ensure_subject_catalog_schema()
    _ensure_table()
    stage = (etapa or "").strip().lower()
    curso = int(curso_asignatura)
    key = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
    if not stage or not key:
        return 0

    rows, _phoras = _calcular_filas_materia_variables(
        etapa=stage,
        curso_asignatura=curso,
        materia_key=key,
        sesion=sesion,
        pendiente=pendiente,
    )

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TABLE}
                WHERE etapa = %s
                  AND curso_asignatura = %s
                  AND materia_key = %s
                """,
                (stage, curso, key),
            )
            if rows:
                cur.executemany(
                    f"""
                    INSERT INTO {TABLE} (
                        etapa, curso_asignatura, materia_key,
                        criterio, descriptor, cruce, ppd, dototal, donumcru,
                        coef0, coef1, sumcoef1, coef2, phoras
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )
    _rebuild_alumno_descriptor_after_materia_variables(
        etapa=stage,
        curso_asignatura=curso,
        materia_key=key,
    )
    return len(rows)


def _rebuild_alumno_descriptor_after_materia_variables(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> None:
    from db.competencias_recalc import refresh_do_pesos_materia
    from db.competencias_alumno_descriptor import rebuild_alumno_descriptor_materia

    refresh_do_pesos_materia(
        etapa=etapa,
        curso_asignatura=curso_asignatura,
        materia_key=materia_key,
    )
    rebuild_alumno_descriptor_materia(
        etapa=etapa,
        curso_asignatura=curso_asignatura,
        materia_key=materia_key,
    )


def rebuild_variables_for_keys(
    keys: list[tuple[str, int, str]],
) -> int:
    """Recalcula solo las materias indicadas (etapa, curso, materia_key)."""
    seen: set[tuple[str, int, str]] = set()
    total = 0
    for etapa, curso, materia_key in keys:
        stage = (etapa or "").strip().lower()
        key = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
        ident = (stage, int(curso), key)
        if not stage or not key or ident in seen:
            continue
        seen.add(ident)
        total += rebuild_materia_variables(
            etapa=stage,
            curso_asignatura=int(curso),
            materia_key=key,
        )
    return total


def rebuild_variables_for_etapa(etapa: str) -> int:
    """Recalcula variables de todas las materias con criterios en la etapa."""
    stage = (etapa or "").strip().lower()
    if not stage:
        return 0
    ensure_competencias_materia_criterios_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT etapa, curso_asignatura, materia_key
                FROM competencias_materia_criterios
                WHERE etapa = %s
                """,
                (stage,),
            )
            keys = [
                (str(r["etapa"]), int(r["curso_asignatura"]), str(r["materia_key"]))
                for r in cur.fetchall()
            ]
    return rebuild_variables_for_keys(keys)


def sync_all_materia_variables() -> int:
    """Recalcula variables para todas las materias con criterios.

    No se llama al arrancar. Uso puntual (p. ej. migración o botón de Cálculos).
    """
    ensure_competencias_materia_criterios_schema()
    _ensure_table()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT etapa, curso_asignatura, materia_key
                FROM competencias_materia_criterios
                ORDER BY etapa, curso_asignatura, materia_key
                """
            )
            materias = [dict(r) for r in cur.fetchall()]

    total = 0
    for m in materias:
        total += rebuild_materia_variables(
            etapa=str(m["etapa"]),
            curso_asignatura=int(m["curso_asignatura"]),
            materia_key=str(m["materia_key"]),
        )
    return total


COEF_CAMPOS: frozenset[str] = frozenset({"coef0", "coef1", "coef2"})


def map_coef_materia(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
    campo: str,
) -> dict[tuple[str, str], Decimal]:
    """Mapa (descriptor_norm, criterio) → valor de coef0, coef1 o coef2."""
    col = (campo or "").strip().lower()
    if col not in COEF_CAMPOS:
        return {}
    ensure_competencias_materia_variables_schema()
    stage = (etapa or "").strip().lower()
    curso = int(curso_asignatura)
    raw = (materia_key or "").strip()
    keys: list[str] = []
    for k in (raw, competencias_materia_group_key(raw) or ""):
        if k and k not in keys:
            keys.append(k)
    out: dict[tuple[str, str], Decimal] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            for key in keys:
                cur.execute(
                    f"""
                    SELECT criterio, descriptor, {col}
                    FROM {TABLE}
                    WHERE etapa = %s
                      AND curso_asignatura = %s
                      AND materia_key = %s
                    """,
                    (stage, curso, key),
                )
                rows = cur.fetchall()
                if rows:
                    for r in rows:
                        crit = str(r.get("criterio") or "").strip()
                        desc = normalize_descriptor_code(str(r.get("descriptor") or ""))
                        val = r.get(col)
                        if not crit or not desc or val is None:
                            continue
                        out[(desc, crit)] = Decimal(str(val))
                    return out
    return out
