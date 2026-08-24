"""Notas enteras editadas en sesión de evaluación (materias y competencias)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from db.connection import get_db

TABLE = "competencias_sesion_notas"

SCOPE_MATERIA = "materia"
SCOPE_COMPETENCIA = "competencia"
SCOPE_VALORES = (SCOPE_MATERIA, SCOPE_COMPETENCIA)

_schema_ready = False


def _norm_alumno(nombre: str) -> str:
    return " ".join((nombre or "").strip().split()).casefold()


def _norm_sesion(sesion: str | None) -> str:
    return (sesion or "").strip().lower()


def materia_scope_key(*, etapa: str, curso: int, materia_key: str) -> str:
    etapa_v = (etapa or "").strip().lower()
    key = (materia_key or "").strip()
    return f"{etapa_v}|{int(curso)}|{key}"


def parse_nota_sesion_entera(raw: object, *, cualitativa: bool = False) -> int | None:
    """Nota de sesión. Vacío → None (borrar override). En ESO: IN/SU/BI/NT/SB."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if cualitativa:
        from db.competencias_evaluacion import parse_nota_acta

        value = parse_nota_acta(text, cualitativa=True)
        return int(value) if value is not None else None
    try:
        value = Decimal(text.replace(",", "."))
    except (InvalidOperation, ValueError):
        raise ValueError("La nota debe ser un entero entre 0 y 10") from None
    if value < 0 or value > 10 or value != value.to_integral_value():
        raise ValueError("La nota debe ser un entero entre 0 y 10")
    return int(value.to_integral_value())


def ensure_competencias_sesion_notas_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    grupo TEXT NOT NULL,
                    sesion TEXT NOT NULL DEFAULT '',
                    alumno TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    scope_key TEXT NOT NULL,
                    nota SMALLINT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_by INTEGER,
                    PRIMARY KEY (grupo, sesion, alumno, scope, scope_key),
                    CONSTRAINT {TABLE}_scope CHECK (
                        scope IN ('{SCOPE_MATERIA}', '{SCOPE_COMPETENCIA}')
                    ),
                    CONSTRAINT {TABLE}_nota CHECK (nota >= 0 AND nota <= 10)
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_csn_grupo_sesion
                ON {TABLE} (LOWER(TRIM(grupo)), sesion)
                """
            )
    _schema_ready = True


def mapa_overrides_sesion(
    grupo: str,
    *,
    sesion: str | None = None,
) -> dict[str, dict[tuple[str, str], int]]:
    """Mapa alumno_norm → {(scope, scope_key): nota_entera}."""
    ensure_competencias_sesion_notas_schema()
    nombre = (grupo or "").strip()
    ses = _norm_sesion(sesion)
    out: dict[str, dict[tuple[str, str], int]] = {}
    if not nombre:
        return out
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT alumno, scope, scope_key, nota
                FROM {TABLE}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                  AND sesion = %s
                """,
                (nombre, ses),
            )
            for r in cur.fetchall():
                al = _norm_alumno(str(r.get("alumno") or ""))
                scope = str(r.get("scope") or "").strip().lower()
                skey = str(r.get("scope_key") or "").strip()
                if not al or scope not in SCOPE_VALORES or not skey:
                    continue
                try:
                    nota = int(r["nota"])
                except (TypeError, ValueError):
                    continue
                out.setdefault(al, {})[(scope, skey)] = nota
    return out


def guardar_override_sesion(
    *,
    grupo: str,
    sesion: str | None,
    alumno: str,
    scope: str,
    scope_key: str,
    nota: int | None,
    updated_by: int | None = None,
) -> bool:
    """Guarda override. Si nota es None, elimina la fila. Devuelve True si queda editada."""
    ensure_competencias_sesion_notas_schema()
    grupo_v = (grupo or "").strip()
    al = (alumno or "").strip()
    ses = _norm_sesion(sesion)
    scope_v = (scope or "").strip().lower()
    skey = (scope_key or "").strip()
    if not grupo_v or not al or scope_v not in SCOPE_VALORES or not skey:
        raise ValueError("Datos de sesión incompletos")
    with get_db() as conn:
        with conn.cursor() as cur:
            if nota is None:
                cur.execute(
                    f"""
                    DELETE FROM {TABLE}
                    WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                      AND sesion = %s
                      AND LOWER(TRIM(alumno)) = LOWER(TRIM(%s))
                      AND scope = %s
                      AND scope_key = %s
                    """,
                    (grupo_v, ses, al, scope_v, skey),
                )
                return False
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    grupo, sesion, alumno, scope, scope_key, nota,
                    updated_at, updated_by
                )
                VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s)
                ON CONFLICT (grupo, sesion, alumno, scope, scope_key)
                DO UPDATE SET
                    nota = EXCLUDED.nota,
                    updated_at = NOW(),
                    updated_by = EXCLUDED.updated_by
                """,
                (grupo_v, ses, al, scope_v, skey, int(nota), updated_by),
            )
    return True


def override_o_none(
    overrides: dict[tuple[str, str], int],
    *,
    scope: str,
    scope_key: str,
) -> int | None:
    return overrides.get(((scope or "").strip().lower(), (scope_key or "").strip()))
