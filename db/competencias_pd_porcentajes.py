"""Porcentajes de la programación didáctica por criterio de evaluación."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction
from typing import Any

from db.connection import get_db
from db.competencias_materia_criterios import (
    list_criterios_materia,
    map_criterios_codes_por_materia,
)
from db.enrolled_subject_catalog import competencias_materia_group_key

TABLE = "competencias_materia_pd_porcentajes"

_schema_ready = False


def ensure_competencias_pd_porcentajes_schema() -> None:
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
                    criterio TEXT NOT NULL,
                    porcentaje NUMERIC(16, 10) NOT NULL,
                    porcentaje_num BIGINT,
                    porcentaje_den BIGINT,
                    modo_reparto TEXT,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_by INTEGER,
                    PRIMARY KEY (etapa, curso_asignatura, materia_key, criterio)
                )
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ALTER COLUMN porcentaje TYPE NUMERIC(16, 10)
                USING porcentaje::numeric(16, 10)
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS porcentaje_num BIGINT
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS porcentaje_den BIGINT
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS modo_reparto TEXT
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS mismos_pesos_extra BOOLEAN
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS porcentaje_extra NUMERIC(16, 10)
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS porcentaje_num_extra BIGINT
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS porcentaje_den_extra BIGINT
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS mismos_pesos_pendiente BOOLEAN
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS porcentaje_pendiente NUMERIC(16, 10)
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS porcentaje_num_pendiente BIGINT
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS porcentaje_den_pendiente BIGINT
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_cmpd_materia
                ON {TABLE} (etapa, curso_asignatura, materia_key)
                """
            )
    _schema_ready = True


def _frac_to_decimal(frac: Fraction) -> Decimal:
    return Decimal(frac.numerator) / Decimal(frac.denominator)


def _as_fraction(value: Fraction | Decimal | float | int) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, Decimal):
        return Fraction(value)
    return Fraction(Decimal(str(value)))


def _format_decimal_text(frac: Fraction, *, comma: bool) -> str:
    d = _frac_to_decimal(frac)
    text = format(d, "f").rstrip("0").rstrip(".")
    if not text:
        text = "0"
    return text.replace(".", ",") if comma else text


def format_pct_display(value: Decimal | Fraction | float | None) -> str | None:
    """Pantalla: 2 decimales con redondeo comercial (3,125 → 3,13)."""
    if value is None:
        return None
    d = _frac_to_decimal(_as_fraction(value))
    q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:.2f}".replace(".", ",")


def format_pct_input(value: Decimal | Fraction | float | None) -> str | None:
    """Igual que display, con punto (input type=number)."""
    if value is None:
        return None
    d = _frac_to_decimal(_as_fraction(value))
    q = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:.2f}"


def _parse_porcentaje(raw: object) -> Fraction | None:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", ".").replace("%", "").strip()
    if not text:
        return None
    try:
        if "/" in text:
            left, right = text.split("/", 1)
            frac = Fraction(int(left.strip()), int(right.strip()))
        else:
            frac = Fraction(
                Decimal(text).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            )
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None
    if frac < 0 or frac > 100:
        return None
    return frac


def _suma_porcentajes(valores: dict[str, Fraction | Decimal]) -> Fraction:
    total = Fraction(0)
    for v in valores.values():
        total += _as_fraction(v)
    return total


def _require_suma_100(
    parsed: dict[str, Fraction | Decimal],
) -> tuple[dict[str, Fraction] | None, str | None]:
    as_frac = {k: _as_fraction(v) for k, v in parsed.items()}
    total = _suma_porcentajes(as_frac)
    if total != 100:
        shown = format_pct_display(_frac_to_decimal(total)) or str(total)
        return None, f"La suma de porcentajes debe ser 100 % (ahora {shown} %)."
    return as_frac, None


def _frac_from_row(row: dict[str, Any]) -> Fraction:
    num = row.get("porcentaje_num")
    den = row.get("porcentaje_den")
    if num is not None and den not in (None, 0):
        try:
            return Fraction(int(num), int(den))
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return Fraction(Decimal(str(row.get("porcentaje") or 0)))


def materia_puede_ser_pendiente(etapa: str, curso_asignatura: int) -> bool:
    """2.º Bach y 4.º ESO no pueden ser pendientes; el resto de ESO/Bach sí."""
    etapa_v = (etapa or "").strip().lower()
    try:
        curso = int(curso_asignatura)
    except (TypeError, ValueError):
        return False
    if etapa_v == "eso":
        return curso in (1, 2, 3)
    if etapa_v in ("bach", "bachillerato"):
        return curso == 1
    return False


def _frac_from_row_named(
    row: dict[str, Any], *, num_key: str, den_key: str, val_key: str
) -> Fraction | None:
    num = row.get(num_key)
    den = row.get(den_key)
    if num is not None and den not in (None, 0):
        try:
            return Fraction(int(num), int(den))
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    val = row.get(val_key)
    if val is None:
        return None
    return Fraction(Decimal(str(val)))


def _frac_from_row_extra(row: dict[str, Any]) -> Fraction | None:
    return _frac_from_row_named(
        row,
        num_key="porcentaje_num_extra",
        den_key="porcentaje_den_extra",
        val_key="porcentaje_extra",
    )


def _frac_from_row_pendiente(row: dict[str, Any]) -> Fraction | None:
    return _frac_from_row_named(
        row,
        num_key="porcentaje_num_pendiente",
        den_key="porcentaje_den_pendiente",
        val_key="porcentaje_pendiente",
    )


def list_porcentajes_materia(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
    sesion: str | None = None,
    pendiente: bool = False,
) -> dict[str, Decimal]:
    ensure_competencias_pd_porcentajes_schema()
    raw = (materia_key or "").strip()
    keys: list[str] = []
    for k in (raw, competencias_materia_group_key(raw) or ""):
        if k and k not in keys:
            keys.append(k)
    use_extra = (sesion or "").strip().lower() == "extraordinaria"
    with get_db() as conn:
        with conn.cursor() as cur:
            for key in keys:
                cur.execute(
                    f"""
                    SELECT criterio, porcentaje, porcentaje_num, porcentaje_den,
                           mismos_pesos_extra, porcentaje_extra,
                           porcentaje_num_extra, porcentaje_den_extra,
                           mismos_pesos_pendiente, porcentaje_pendiente,
                           porcentaje_num_pendiente, porcentaje_den_pendiente
                    FROM {TABLE}
                    WHERE etapa = %s
                      AND curso_asignatura = %s
                      AND materia_key = %s
                    """,
                    ((etapa or "").strip().lower(), int(curso_asignatura), key),
                )
                rows = cur.fetchall()
                if rows:
                    out: dict[str, Decimal] = {}
                    for r in rows:
                        crit = str(r["criterio"] or "").strip()
                        if not crit:
                            continue
                        mismos_extra = r.get("mismos_pesos_extra")
                        if mismos_extra is None:
                            mismos_extra = True
                        mismos_pend = r.get("mismos_pesos_pendiente")
                        if mismos_pend is None:
                            mismos_pend = True
                        frac = None
                        if pendiente and not bool(mismos_pend):
                            frac = _frac_from_row_pendiente(r)
                        elif use_extra and not bool(mismos_extra):
                            frac = _frac_from_row_extra(r)
                        if frac is None:
                            frac = _frac_from_row(r)
                        out[crit] = _frac_to_decimal(frac)
                    return out
    return {}


def get_mismos_pesos_extra(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> bool:
    """True si ordinaria y extraordinaria comparten los mismos pesos (por defecto)."""
    ensure_competencias_pd_porcentajes_schema()
    raw = (materia_key or "").strip()
    keys: list[str] = []
    for k in (raw, competencias_materia_group_key(raw) or ""):
        if k and k not in keys:
            keys.append(k)
    with get_db() as conn:
        with conn.cursor() as cur:
            for key in keys:
                cur.execute(
                    f"""
                    SELECT mismos_pesos_extra
                    FROM {TABLE}
                    WHERE etapa = %s
                      AND curso_asignatura = %s
                      AND materia_key = %s
                    LIMIT 1
                    """,
                    ((etapa or "").strip().lower(), int(curso_asignatura), key),
                )
                row = cur.fetchone()
                if row:
                    val = row.get("mismos_pesos_extra")
                    if val is None:
                        return True
                    return bool(val)
    return True


def get_mismos_pesos_pendiente(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> bool:
    """True si los pesos de pendiente coinciden con los de la materia (por defecto)."""
    ensure_competencias_pd_porcentajes_schema()
    raw = (materia_key or "").strip()
    keys: list[str] = []
    for k in (raw, competencias_materia_group_key(raw) or ""):
        if k and k not in keys:
            keys.append(k)
    with get_db() as conn:
        with conn.cursor() as cur:
            for key in keys:
                cur.execute(
                    f"""
                    SELECT mismos_pesos_pendiente
                    FROM {TABLE}
                    WHERE etapa = %s
                      AND curso_asignatura = %s
                      AND materia_key = %s
                    LIMIT 1
                    """,
                    ((etapa or "").strip().lower(), int(curso_asignatura), key),
                )
                row = cur.fetchone()
                if row:
                    val = row.get("mismos_pesos_pendiente")
                    if val is None:
                        return True
                    return bool(val)
    return True


def _detect_modo_reparto(
    *,
    criterios_rows: list[dict[str, Any]],
    pcts: dict[str, Decimal],
) -> str:
    codes = [
        str(r.get("criterio") or "").strip()
        for r in criterios_rows
        if str(r.get("criterio") or "").strip()
    ]
    if not codes or set(codes) - set(pcts):
        return "libre"
    stored = {c: _as_fraction(pcts[c]) for c in codes}
    if stored == repartir_por_criterios(codes):
        return "criterios"
    if stored == repartir_por_competencias_especificas(criterios_rows):
        return "ce"
    return "libre"


def get_modo_reparto(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
    criterios_rows: list[dict[str, Any]] | None = None,
) -> str:
    """Modo con el que se guardó la PD (criterios / ce / libre)."""
    ensure_competencias_pd_porcentajes_schema()
    raw = (materia_key or "").strip()
    keys: list[str] = []
    for k in (raw, competencias_materia_group_key(raw) or ""):
        if k and k not in keys:
            keys.append(k)
    with get_db() as conn:
        with conn.cursor() as cur:
            for key in keys:
                cur.execute(
                    f"""
                    SELECT modo_reparto
                    FROM {TABLE}
                    WHERE etapa = %s
                      AND curso_asignatura = %s
                      AND materia_key = %s
                      AND modo_reparto IS NOT NULL
                    LIMIT 1
                    """,
                    ((etapa or "").strip().lower(), int(curso_asignatura), key),
                )
                row = cur.fetchone()
                if row:
                    modo = str(row.get("modo_reparto") or "").strip().lower()
                    if modo in ("libre", "criterios", "ce"):
                        return modo
    pcts = list_porcentajes_materia(
        etapa=etapa,
        curso_asignatura=curso_asignatura,
        materia_key=materia_key,
    )
    if not pcts:
        return "libre"
    rows = criterios_rows or list_criterios_materia(
        etapa=etapa,
        curso_asignatura=curso_asignatura,
        materia_key=materia_key,
    )
    return _detect_modo_reparto(criterios_rows=rows, pcts=pcts)


def replace_porcentajes_materia(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
    porcentajes: dict[str, Fraction | Decimal],
    updated_by: int | None = None,
    modo_reparto: str = "libre",
    mismos_pesos_extra: bool = True,
    porcentajes_extra: dict[str, Fraction | Decimal] | None = None,
    mismos_pesos_pendiente: bool = True,
    porcentajes_pendiente: dict[str, Fraction | Decimal] | None = None,
) -> None:
    ensure_competencias_pd_porcentajes_schema()
    etapa_v = (etapa or "").strip().lower()
    curso = int(curso_asignatura)
    key = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
    if not key:
        raise ValueError("Materia no válida")
    parsed_ok, err = _require_suma_100(porcentajes)
    if err or parsed_ok is None:
        raise ValueError(err or "La suma de porcentajes debe ser 100 %.")
    mismos = bool(mismos_pesos_extra)
    extra_ok: dict[str, Fraction] | None = None
    if mismos:
        extra_ok = dict(parsed_ok)
    else:
        if not porcentajes_extra:
            raise ValueError(
                "Indique los porcentajes de la extraordinaria o marque que son los mismos."
            )
        extra_ok, err_x = _require_suma_100(porcentajes_extra)
        if err_x or extra_ok is None:
            raise ValueError(
                (err_x or "La suma de porcentajes de la extraordinaria debe ser 100 %.")
                .replace("porcentajes debe", "porcentajes de la extraordinaria debe")
            )
    mismos_p = bool(mismos_pesos_pendiente)
    pend_ok: dict[str, Fraction] | None = None
    if mismos_p:
        pend_ok = dict(parsed_ok)
    else:
        if not porcentajes_pendiente:
            raise ValueError(
                "Indique los porcentajes de la materia pendiente o marque que son los mismos."
            )
        pend_ok, err_p = _require_suma_100(porcentajes_pendiente)
        if err_p or pend_ok is None:
            raise ValueError(
                (err_p or "La suma de porcentajes de la pendiente debe ser 100 %.")
                .replace("porcentajes debe", "porcentajes de la pendiente debe")
            )
    modo_v = (modo_reparto or "libre").strip().lower()
    if modo_v in ("ce", "competencias", "competencias_especificas"):
        modo_v = "ce"
    if modo_v not in ("libre", "criterios", "ce"):
        modo_v = "libre"

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                DELETE FROM {TABLE}
                WHERE etapa = %s
                  AND curso_asignatura = %s
                  AND materia_key = %s
                """,
                (etapa_v, curso, key),
            )
            for criterio, pct in parsed_ok.items():
                crit = (criterio or "").strip()
                if not crit:
                    continue
                frac = _as_fraction(pct)
                frac_x = _as_fraction(extra_ok.get(crit, frac)) if extra_ok else frac
                frac_p = _as_fraction(pend_ok.get(crit, frac)) if pend_ok else frac
                cur.execute(
                    f"""
                    INSERT INTO {TABLE} (
                        etapa, curso_asignatura, materia_key, criterio,
                        porcentaje, porcentaje_num, porcentaje_den, modo_reparto,
                        mismos_pesos_extra,
                        porcentaje_extra, porcentaje_num_extra, porcentaje_den_extra,
                        mismos_pesos_pendiente,
                        porcentaje_pendiente, porcentaje_num_pendiente,
                        porcentaje_den_pendiente,
                        updated_at, updated_by
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, NOW(), %s
                    )
                    """,
                    (
                        etapa_v,
                        curso,
                        key,
                        crit,
                        _frac_to_decimal(frac),
                        frac.numerator,
                        frac.denominator,
                        modo_v,
                        mismos,
                        _frac_to_decimal(frac_x),
                        frac_x.numerator,
                        frac_x.denominator,
                        mismos_p,
                        _frac_to_decimal(frac_p),
                        frac_p.numerator,
                        frac_p.denominator,
                        updated_by,
                    ),
                )

    from db.competencias_materia_variables import rebuild_materia_variables

    rebuild_materia_variables(
        etapa=etapa_v,
        curso_asignatura=curso,
        materia_key=key,
    )


def validate_porcentajes_form(
    *,
    criterios: list[str],
    form_values: dict[str, object],
    prefix: str = "pct_",
    etiqueta: str = "",
) -> tuple[dict[str, Fraction] | None, str | None]:
    """Devuelve (mapa criterio→%, error). Los % deben sumar 100 (modo libre)."""
    parsed: dict[str, Fraction] = {}
    suf = f" de la {etiqueta}" if etiqueta else ""
    for crit in criterios:
        raw = form_values.get(f"{prefix}{crit}", form_values.get(crit) if prefix == "pct_" else None)
        value = _parse_porcentaje(raw)
        if value is None:
            return None, f"Porcentaje no válido{suf} para el criterio {crit}."
        parsed[crit] = value
    as_frac, err = _require_suma_100(parsed)
    if err and etiqueta:
        err = err.replace("porcentajes debe", f"porcentajes de la {etiqueta} debe")
    return as_frac, err


def resolve_porcentajes_guardar(
    *,
    modo: str,
    criterios_rows: list[dict[str, Any]],
    form_values: dict[str, object],
) -> tuple[dict[str, Fraction] | None, str | None]:
    """Según modo: fracciones exactas (criterios/CE) o pesos libres del formulario."""
    modo_v = (modo or "libre").strip().lower()
    codes = [
        str(r.get("criterio") or "").strip()
        for r in criterios_rows
        if str(r.get("criterio") or "").strip()
    ]
    if not codes:
        return None, "No hay criterios para esta materia."
    if modo_v == "criterios":
        return _require_suma_100(repartir_por_criterios(codes))
    if modo_v in ("ce", "competencias", "competencias_especificas"):
        return _require_suma_100(repartir_por_competencias_especificas(criterios_rows))
    return validate_porcentajes_form(criterios=codes, form_values=form_values)


def set_materias_con_porcentajes_pd(*, etapa: str) -> set[tuple[int, str]]:
    """Pares (curso, materia_key) con PD completa (todos los criterios, suma 100)."""
    ensure_competencias_pd_porcentajes_schema()
    etapa_v = (etapa or "").strip().lower()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT curso_asignatura, materia_key, criterio,
                       porcentaje, porcentaje_num, porcentaje_den
                FROM {TABLE}
                WHERE etapa = %s
                """,
                (etapa_v,),
            )
            by_mat: dict[tuple[int, str], dict[str, Fraction]] = {}
            for r in cur.fetchall():
                curso = int(r["curso_asignatura"])
                key = str(r["materia_key"] or "").strip()
                crit = str(r["criterio"] or "").strip()
                if not key or not crit:
                    continue
                gkey = (curso, key)
                by_mat.setdefault(gkey, {})[crit] = _frac_from_row(r)

    criterios_map = map_criterios_codes_por_materia(etapa=etapa_v)
    out: set[tuple[int, str]] = set()
    for (curso, key), pcts in by_mat.items():
        needed = criterios_map.get((curso, key))
        if not needed:
            fam_key = competencias_materia_group_key(key) or key
            if fam_key != key:
                needed = criterios_map.get((curso, fam_key))
        if not needed or needed - set(pcts):
            continue
        total = sum((pcts[c] for c in needed), Fraction(0))
        if total != 100:
            continue
        out.add((curso, key))
        fam = competencias_materia_group_key(key) or key
        out.add((curso, fam))
    return out


def split_equal_total(
    n: int,
    *,
    total: Fraction | Decimal | int = 100,
) -> list[Fraction]:
    """Reparte ``total`` en ``n`` fracciones exactas e iguales (p. ej. 100/32)."""
    if n <= 0:
        return []
    part = _as_fraction(total) / n
    return [part] * n


def repartir_por_criterios(criterios: list[str]) -> dict[str, Fraction]:
    """100 % a partes iguales: cada criterio = 100/n."""
    codes = [c for c in ((x or "").strip() for x in criterios) if c]
    parts = split_equal_total(len(codes))
    return {code: parts[i] for i, code in enumerate(codes)}


def repartir_por_competencias_especificas(
    rows: list[dict[str, Any]],
) -> dict[str, Fraction]:
    """100/n_CE por competencia; dentro de cada CE, 1/n_criterios de esa parte."""
    by_ce: dict[int, list[str]] = {}
    order_ce: list[int] = []
    for row in rows:
        crit = str(row.get("criterio") or "").strip()
        if not crit:
            continue
        try:
            ce = int(row.get("competencia_especifica") or 0)
        except (TypeError, ValueError):
            ce = 0
        if not ce:
            head = crit.split(".", 1)[0]
            try:
                ce = int(head)
            except ValueError:
                ce = 0
        if ce not in by_ce:
            by_ce[ce] = []
            order_ce.append(ce)
        by_ce[ce].append(crit)

    if not order_ce:
        return {}

    ce_parts = split_equal_total(len(order_ce))
    out: dict[str, Fraction] = {}
    for i, ce in enumerate(order_ce):
        crits = by_ce[ce]
        share = ce_parts[i]
        crit_parts = split_equal_total(len(crits), total=share)
        for j, crit in enumerate(crits):
            out[crit] = crit_parts[j]
    return out


def criterios_con_porcentajes(
    *,
    etapa: str,
    curso_asignatura: int,
    materia_key: str,
) -> list[dict[str, Any]]:
    """Lista de criterios con porcentaje actual (None si no hay)."""
    criterios = list_criterios_materia(
        etapa=etapa,
        curso_asignatura=curso_asignatura,
        materia_key=materia_key,
    )
    pcts = list_porcentajes_materia(
        etapa=etapa,
        curso_asignatura=curso_asignatura,
        materia_key=materia_key,
    )
    extras = list_porcentajes_materia(
        etapa=etapa,
        curso_asignatura=curso_asignatura,
        materia_key=materia_key,
        sesion="extraordinaria",
    )
    pends = list_porcentajes_materia(
        etapa=etapa,
        curso_asignatura=curso_asignatura,
        materia_key=materia_key,
        pendiente=True,
    )
    out: list[dict[str, Any]] = []
    for row in criterios:
        crit = str(row.get("criterio") or "").strip()
        try:
            ce = int(row.get("competencia_especifica") or 0)
        except (TypeError, ValueError):
            ce = 0
        frac = _as_fraction(pcts[crit]) if crit in pcts else None
        frac_x = _as_fraction(extras[crit]) if crit in extras else None
        frac_p = _as_fraction(pends[crit]) if crit in pends else None
        out.append(
            {
                "criterio": crit,
                "competencia_especifica": ce,
                "porcentaje": float(pcts[crit]) if crit in pcts else None,
                "porcentaje_display": format_pct_display(frac) if frac is not None else None,
                "porcentaje_input": format_pct_input(frac) if frac is not None else None,
                "porcentaje_extra_display": (
                    format_pct_display(frac_x) if frac_x is not None else None
                ),
                "porcentaje_extra_input": (
                    format_pct_input(frac_x) if frac_x is not None else None
                ),
                "porcentaje_pendiente_display": (
                    format_pct_display(frac_p) if frac_p is not None else None
                ),
                "porcentaje_pendiente_input": (
                    format_pct_input(frac_p) if frac_p is not None else None
                ),
            }
        )
    return out
