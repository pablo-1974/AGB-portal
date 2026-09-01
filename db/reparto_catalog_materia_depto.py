"""Mapa materializado materia→departamento para Reparto (evita scan del catálogo)."""

from __future__ import annotations

from db.connection import get_db
from db.enrolled_subject_catalog import normalize_catalog_etapa

TABLE = "reparto_catalog_materia_depto"
_schema_ready = False


def ensure_reparto_catalog_materia_depto_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    etapa TEXT NOT NULL,
                    curso_asignatura INTEGER NOT NULL,
                    materia_abrev TEXT NOT NULL,
                    departamento TEXT NOT NULL,
                    PRIMARY KEY (etapa, curso_asignatura, materia_abrev)
                )
                """
            )
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_reparto_cat_mab
                ON {TABLE} (etapa, curso_asignatura, materia_abrev)
                """
            )
    _schema_ready = True


def refresh_reparto_catalog_materia_depto() -> int:
    """Sincroniza desde enrolled_subject_catalog. Devuelve filas insertadas."""
    ensure_reparto_catalog_materia_depto_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {TABLE}")
            cur.execute(
                """
                SELECT etapa, curso_asignatura, materia_abrev, departamento
                FROM enrolled_subject_catalog
                WHERE TRIM(COALESCE(departamento, '')) <> ''
                  AND TRIM(COALESCE(materia_abrev, '')) <> ''
                  AND curso_asignatura IS NOT NULL
                """
            )
            rows = cur.fetchall()
            n = 0
            for r in rows:
                etapa = normalize_catalog_etapa(str(r.get("etapa") or "")) or (
                    str(r.get("etapa") or "").strip().lower()
                )
                try:
                    curso = int(r["curso_asignatura"])
                except (TypeError, ValueError):
                    continue
                mab = str(r.get("materia_abrev") or "").strip().lower()
                dep = str(r.get("departamento") or "").strip()
                if not etapa or not mab or not dep:
                    continue
                cur.execute(
                    f"""
                    INSERT INTO {TABLE} (etapa, curso_asignatura, materia_abrev, departamento)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (etapa, curso_asignatura, materia_abrev) DO UPDATE
                    SET departamento = EXCLUDED.departamento
                    """,
                    (etapa, curso, mab, dep),
                )
                n += 1
    return n


def get_catalog_materia_depto_map() -> dict[str, str]:
    """Clave ``etapa|curso|materia_abrev`` → nombre de departamento."""
    ensure_reparto_catalog_materia_depto_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS n FROM {TABLE}")
            if int(cur.fetchone()["n"]) == 0:
                refresh_reparto_catalog_materia_depto()
            cur.execute(
                f"""
                SELECT etapa, curso_asignatura, materia_abrev, departamento
                FROM {TABLE}
                """
            )
            out: dict[str, str] = {}
            for r in cur.fetchall():
                etapa = str(r.get("etapa") or "").strip()
                curso = int(r["curso_asignatura"])
                mab = str(r.get("materia_abrev") or "").strip().lower()
                key = f"{etapa}|{curso}|{mab}"
                out[key] = str(r.get("departamento") or "").strip()
            return out
