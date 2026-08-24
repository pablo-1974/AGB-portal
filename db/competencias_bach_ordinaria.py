"""Acta de ordinaria congelada por grupo (Bachillerato → extraordinaria)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from db.connection import get_db
from db.enrolled_subject_catalog import competencias_materia_group_key

TABLE = "competencias_bach_ordinaria_acta"

_schema_ready = False


def _norm_alumno(nombre: str) -> str:
    return " ".join((nombre or "").strip().split()).casefold()


def ensure_competencias_bach_ordinaria_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    grupo TEXT NOT NULL,
                    etapa TEXT NOT NULL,
                    curso_asignatura SMALLINT NOT NULL,
                    materia_key TEXT NOT NULL,
                    alumno TEXT NOT NULL,
                    nota NUMERIC(8, 4) NOT NULL,
                    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (
                        grupo, etapa, curso_asignatura, materia_key, alumno
                    )
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_cboa_grupo
                ON {TABLE} (LOWER(TRIM(grupo)))
                """
            )
    _schema_ready = True


def tiene_snapshot_ordinaria(grupo: str) -> bool:
    ensure_competencias_bach_ordinaria_schema()
    nombre = (grupo or "").strip()
    if not nombre:
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT 1 FROM {TABLE}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                LIMIT 1
                """,
                (nombre,),
            )
            return cur.fetchone() is not None


def ensure_snapshot_ordinaria_grupo(grupo: str) -> bool:
    """Copia nota_acta actual al snapshot si el grupo aún no tiene filas."""
    from db.competencias_evaluacion import TABLE_ACTA, ensure_competencias_evaluacion_schema

    ensure_competencias_bach_ordinaria_schema()
    ensure_competencias_evaluacion_schema()
    nombre = (grupo or "").strip()
    if not nombre or tiene_snapshot_ordinaria(nombre):
        return False
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    grupo, etapa, curso_asignatura, materia_key, alumno, nota
                )
                SELECT %s, etapa, curso_asignatura, materia_key, alumno, nota
                FROM {TABLE_ACTA}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                  AND nota IS NOT NULL
                ON CONFLICT DO NOTHING
                """,
                (nombre, nombre),
            )
            return (cur.rowcount or 0) > 0


def mapa_snapshot_ordinaria(
    grupo: str,
) -> dict[tuple[str, int, str], dict[str, Decimal | None]]:
    """(etapa, curso, key) → {alumno_norm: nota}."""
    ensure_competencias_bach_ordinaria_schema()
    nombre = (grupo or "").strip()
    out: dict[tuple[str, int, str], dict[str, Decimal | None]] = {}
    if not nombre:
        return out
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT etapa, curso_asignatura, materia_key, alumno, nota
                FROM {TABLE}
                WHERE LOWER(TRIM(grupo)) = LOWER(TRIM(%s))
                """,
                (nombre,),
            )
            for r in cur.fetchall():
                etapa = str(r.get("etapa") or "").strip().lower()
                key = str(r.get("materia_key") or "").strip()
                al = _norm_alumno(str(r.get("alumno") or ""))
                if not etapa or not key or not al:
                    continue
                try:
                    curso = int(r["curso_asignatura"])
                except (TypeError, ValueError):
                    continue
                nota = Decimal(str(r["nota"])) if r.get("nota") is not None else None
                fam = competencias_materia_group_key(key) or key
                for gkey in ((etapa, curso, key), (etapa, curso, fam)):
                    out.setdefault(gkey, {})[al] = nota
    return out


def nota_snapshot_ordinaria(
    snapshot: dict[tuple[str, int, str], dict[str, Decimal | None]],
    *,
    etapa: str,
    curso: int,
    materia_key: str,
    al_norm: str,
) -> Decimal | None:
    key = competencias_materia_group_key(materia_key) or (materia_key or "").strip()
    etapa_v = (etapa or "").strip().lower()
    por_al = snapshot.get((etapa_v, int(curso), key))
    if por_al is None:
        fam = competencias_materia_group_key(key) or key
        por_al = snapshot.get((etapa_v, int(curso), fam))
    if not por_al:
        return None
    val = por_al.get(al_norm)
    return Decimal(str(val)) if val is not None else None


def aprobado_en_ordinaria(
    nota: Decimal | None,
) -> bool:
    return nota is not None and nota >= Decimal("5")


def list_grupos_con_snapshot_ordinaria() -> list[str]:
    """Grupos Bach con acta de ordinaria congelada."""
    ensure_competencias_bach_ordinaria_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT DISTINCT TRIM(grupo) AS grupo
                FROM {TABLE}
                WHERE TRIM(COALESCE(grupo, '')) <> ''
                ORDER BY 1
                """
            )
            return [
                str(r["grupo"]).strip()
                for r in cur.fetchall()
                if r.get("grupo")
            ]


def mapa_snapshots_todos() -> dict[str, dict[tuple[str, int, str], dict[str, Decimal | None]]]:
    """Todos los snapshots indexados por grupo.casefold() → mapa_snapshot."""
    ensure_competencias_bach_ordinaria_schema()
    out: dict[str, dict[tuple[str, int, str], dict[str, Decimal | None]]] = {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT grupo, etapa, curso_asignatura, materia_key, alumno, nota
                FROM {TABLE}
                """
            )
            for r in cur.fetchall():
                grupo_cf = str(r.get("grupo") or "").strip().casefold()
                etapa = str(r.get("etapa") or "").strip().lower()
                key = str(r.get("materia_key") or "").strip()
                al = _norm_alumno(str(r.get("alumno") or ""))
                if not grupo_cf or not etapa or not key or not al:
                    continue
                try:
                    curso = int(r["curso_asignatura"])
                except (TypeError, ValueError):
                    continue
                nota = Decimal(str(r["nota"])) if r.get("nota") is not None else None
                fam = competencias_materia_group_key(key) or key
                snap = out.setdefault(grupo_cf, {})
                for gkey in ((etapa, curso, key), (etapa, curso, fam)):
                    snap.setdefault(gkey, {})[al] = nota
    return out
