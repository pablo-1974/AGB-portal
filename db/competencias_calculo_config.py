"""Opciones de cálculo de competencias (Configuración)."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Any

from db.connection import get_db

TABLE = "competencias_calculo_config"

PROMEDIO_NO = "no"
PROMEDIO_SI = "si"
PROMEDIO_VALORES = (PROMEDIO_NO, PROMEDIO_SI)
PROMEDIO_DEFAULT = PROMEDIO_NO

PESO_CRUCES_PCT = "cruces_pct"
PESO_CRUCES_PCT_HORAS = "cruces_pct_horas"
PESO_PCT_HORAS = "pct_horas"
PESO_VALORES = (PESO_CRUCES_PCT, PESO_CRUCES_PCT_HORAS, PESO_PCT_HORAS)
PESO_DEFAULT = PESO_PCT_HORAS

DEC_TRUNCAR = "truncar"
DEC_REDONDEAR = "redondear"
DEC_SUSP_TRUNC_APROB_RED = "susp_trunc_aprob_red"
DEC_VALORES = (DEC_TRUNCAR, DEC_REDONDEAR, DEC_SUSP_TRUNC_APROB_RED)
DEC_DEFAULT = DEC_SUSP_TRUNC_APROB_RED

PEND_IGUAL = "igual"
PEND_MITAD = "1_2"
PEND_TERCIO = "1_3"
PEND_CUARTO = "1_4"
PEND_QUINTO = "1_5"
PEND_VALORES = (PEND_IGUAL, PEND_MITAD, PEND_TERCIO, PEND_CUARTO, PEND_QUINTO)
PEND_DEFAULT = PEND_CUARTO
PEND_DIVISOR = {
    PEND_IGUAL: 1,
    PEND_MITAD: 2,
    PEND_TERCIO: 3,
    PEND_CUARTO: 4,
    PEND_QUINTO: 5,
}

DEFAULTS = {
    "promedio_descriptores": PROMEDIO_DEFAULT,
    "peso_periodos": PESO_DEFAULT,
    "tratamiento_pendientes": PEND_DEFAULT,
    "decimales": DEC_DEFAULT,
}

_schema_ready = False


def ensure_competencias_calculo_config_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    id SMALLINT PRIMARY KEY DEFAULT 1,
                    promedio_descriptores TEXT NOT NULL DEFAULT '{PROMEDIO_DEFAULT}',
                    peso_periodos TEXT NOT NULL DEFAULT '{PESO_DEFAULT}',
                    tratamiento_pendientes TEXT NOT NULL DEFAULT '{PEND_DEFAULT}',
                    decimales TEXT NOT NULL DEFAULT '{DEC_DEFAULT}',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT {TABLE}_one_row CHECK (id = 1)
                )
                """
            )
            cur.execute(
                f"""
                INSERT INTO {TABLE} (id)
                VALUES (1)
                ON CONFLICT (id) DO NOTHING
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS tratamiento_pendientes TEXT
                    NOT NULL DEFAULT '{PEND_DEFAULT}'
                """
            )
    _schema_ready = True


def _norm_choice(raw: object, allowed: tuple[str, ...], default: str) -> str:
    val = str(raw or "").strip().lower()
    return val if val in allowed else default


def nivel_coef_desde_peso(peso_periodos: str | None) -> int:
    """0 → coef0, 1 → coef1, 2 → coef2 según la opción de períodos semanales."""
    val = _norm_choice(peso_periodos, PESO_VALORES, PESO_DEFAULT)
    if val == PESO_CRUCES_PCT:
        return 0
    if val == PESO_CRUCES_PCT_HORAS:
        return 1
    return 2


def divisor_pendientes(tratamiento: str | None) -> int:
    """Entero por el que se dividen coef0–2 de una materia pendiente (1 = igual)."""
    val = _norm_choice(tratamiento, PEND_VALORES, PEND_DEFAULT)
    return PEND_DIVISOR.get(val, PEND_DIVISOR[PEND_DEFAULT])


_Q0 = Decimal("1")
_Q2 = Decimal("0.01")


def nota_entera_segun_decimales(
    value: Decimal | float | int,
    modo: str | None,
) -> Decimal:
    """Pasa la nota a entero: truncar, redondear, o truncar < 5 y redondear ≥ 5."""
    d = Decimal(str(value))
    val = _norm_choice(modo, DEC_VALORES, DEC_DEFAULT)
    if val == DEC_TRUNCAR:
        return d.quantize(_Q0, rounding=ROUND_DOWN)
    if val == DEC_REDONDEAR:
        return d.quantize(_Q0, rounding=ROUND_HALF_UP)
    if d < Decimal("5"):
        return d.quantize(_Q0, rounding=ROUND_DOWN)
    return d.quantize(_Q0, rounding=ROUND_HALF_UP)


def format_nota_cc_entera_es(
    value: Decimal | float | int | None,
    modo: str | None = None,
) -> str:
    """Nota de competencia en sesión: entero sin decimales."""
    if value is None:
        return ""
    return format(nota_entera_segun_decimales(value, modo), "f")


def format_nota_cc_2d_es(value: Decimal | float | int | None) -> str:
    """Misma nota redondeada a dos decimales, coma decimal (p. ej. 7,25)."""
    if value is None:
        return ""
    d = Decimal(str(value)).quantize(_Q2, rounding=ROUND_HALF_UP)
    return format(d, "f").replace(".", ",")


def get_calculo_config() -> dict[str, Any]:
    ensure_competencias_calculo_config_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT promedio_descriptores, peso_periodos,
                       tratamiento_pendientes, decimales
                FROM {TABLE}
                WHERE id = 1
                """
            )
            row = cur.fetchone()
    if not row:
        return dict(DEFAULTS)
    return {
        "promedio_descriptores": _norm_choice(
            row.get("promedio_descriptores"), PROMEDIO_VALORES, PROMEDIO_DEFAULT
        ),
        "peso_periodos": _norm_choice(
            row.get("peso_periodos"), PESO_VALORES, PESO_DEFAULT
        ),
        "tratamiento_pendientes": _norm_choice(
            row.get("tratamiento_pendientes"), PEND_VALORES, PEND_DEFAULT
        ),
        "decimales": _norm_choice(row.get("decimales"), DEC_VALORES, DEC_DEFAULT),
    }


def save_calculo_config(
    *,
    promedio_descriptores: str,
    peso_periodos: str,
    tratamiento_pendientes: str,
    decimales: str,
) -> dict[str, Any]:
    ensure_competencias_calculo_config_schema()
    data = {
        "promedio_descriptores": _norm_choice(
            promedio_descriptores, PROMEDIO_VALORES, PROMEDIO_DEFAULT
        ),
        "peso_periodos": _norm_choice(peso_periodos, PESO_VALORES, PESO_DEFAULT),
        "tratamiento_pendientes": _norm_choice(
            tratamiento_pendientes, PEND_VALORES, PEND_DEFAULT
        ),
        "decimales": _norm_choice(decimales, DEC_VALORES, DEC_DEFAULT),
    }
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    id, promedio_descriptores, peso_periodos,
                    tratamiento_pendientes, decimales, updated_at
                )
                VALUES (1, %s, %s, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    promedio_descriptores = EXCLUDED.promedio_descriptores,
                    peso_periodos = EXCLUDED.peso_periodos,
                    tratamiento_pendientes = EXCLUDED.tratamiento_pendientes,
                    decimales = EXCLUDED.decimales,
                    updated_at = NOW()
                """,
                (
                    data["promedio_descriptores"],
                    data["peso_periodos"],
                    data["tratamiento_pendientes"],
                    data["decimales"],
                ),
            )
    return data
