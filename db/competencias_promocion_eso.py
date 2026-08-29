"""Excepcionalidad de promoción ESO (art. 8 Orden EDU/424/2024) en sesión de evaluación."""

from __future__ import annotations

from db.connection import get_db

TABLE = "competencias_promocion_eso"

_schema_ready = False


def _norm_alumno(nombre: str) -> str:
    from utils.text import normalize_alumno_key

    return normalize_alumno_key(nombre)


def _norm_sesion(sesion: str | None) -> str:
    return (sesion or "").strip().lower()


def ensure_competencias_promocion_eso_schema() -> None:
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
                    excepcionalidad BOOLEAN NOT NULL DEFAULT FALSE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_by INTEGER,
                    PRIMARY KEY (grupo, sesion, alumno)
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_cpe_grupo_sesion
                ON {TABLE} (LOWER(TRIM(grupo)), sesion)
                """
            )
    _schema_ready = True


def mapa_excepcionalidad_promocion(
    grupo: str,
    *,
    sesion: str | None = None,
) -> dict[str, bool]:
    """Mapa alumno_norm → excepcionalidad marcada."""
    ensure_competencias_promocion_eso_schema()
    nombre = (grupo or "").strip()
    ses = _norm_sesion(sesion)
    out: dict[str, bool] = {}
    if not nombre:
        return out
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT alumno, excepcionalidad
                FROM {TABLE}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                  AND sesion = %s
                """,
                (nombre, ses),
            )
            for r in cur.fetchall():
                al = _norm_alumno(str(r.get("alumno") or ""))
                if not al:
                    continue
                out[al] = bool(r.get("excepcionalidad"))
    return out


def guardar_excepcionalidad_promocion(
    *,
    grupo: str,
    sesion: str | None,
    alumno: str,
    excepcionalidad: bool,
    updated_by: int | None = None,
) -> bool:
    """Guarda o borra el flag. Devuelve el valor efectivo."""
    ensure_competencias_promocion_eso_schema()
    grupo_v = (grupo or "").strip()
    al = (alumno or "").strip()
    ses = _norm_sesion(sesion)
    if not grupo_v or not al:
        raise ValueError("Alumno o grupo no indicado")
    flag = bool(excepcionalidad)
    with get_db() as conn:
        with conn.cursor() as cur:
            if not flag:
                cur.execute(
                    f"""
                    DELETE FROM {TABLE}
                    WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                      AND sesion = %s
                      AND LOWER(TRIM(alumno)) = LOWER(TRIM(%s))
                    """,
                    (grupo_v, ses, al),
                )
                return False
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    grupo, sesion, alumno, excepcionalidad,
                    updated_at, updated_by
                )
                VALUES (%s, %s, %s, TRUE, NOW(), %s)
                ON CONFLICT (grupo, sesion, alumno)
                DO UPDATE SET
                    excepcionalidad = TRUE,
                    updated_at = NOW(),
                    updated_by = EXCLUDED.updated_by
                """,
                (grupo_v, ses, al, updated_by),
            )
    return True
