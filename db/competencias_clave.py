"""Competencias clave (LOMLOE) para la app de evaluación."""

from __future__ import annotations

from typing import Any

from db.connection import get_db

TABLE = "competencias_clave"

# Orden oficial LOMLOE / currículo.
COMPETENCIAS_CLAVE_SEED: tuple[dict[str, str], ...] = (
    {
        "abreviatura": "CCL",
        "nombre": "Competencia en comunicación lingüística",
    },
    {
        "abreviatura": "CP",
        "nombre": "Competencia plurilingüe",
    },
    {
        "abreviatura": "STEM",
        "nombre": (
            "Competencia matemática y competencia en ciencia, "
            "tecnología e ingeniería"
        ),
    },
    {
        "abreviatura": "CD",
        "nombre": "Competencia digital",
    },
    {
        "abreviatura": "CPSAA",
        "nombre": "Competencia personal, social y de aprender a aprender",
    },
    {
        "abreviatura": "CC",
        "nombre": "Competencia ciudadana",
    },
    {
        "abreviatura": "CE",
        "nombre": "Competencia emprendedora",
    },
    {
        "abreviatura": "CCEC",
        "nombre": "Competencia en conciencia y expresión culturales",
    },
)

# Descriptores operativos oficiales por competencia y etapa.
DESCRIPTORES_ESO: dict[str, tuple[str, ...]] = {
    "CCL": ("CCL 1", "CCL 2", "CCL 3", "CCL 4", "CCL 5"),
    "CP": ("CP 1", "CP 2", "CP 3"),
    "STEM": ("STEM 1", "STEM 2", "STEM 3", "STEM 4", "STEM 5"),
    "CD": ("CD 1", "CD 2", "CD 3", "CD 4", "CD 5"),
    "CPSAA": ("CPSAA 1", "CPSAA 2", "CPSAA 3", "CPSAA 4", "CPSAA 5"),
    "CC": ("CC 1", "CC 2", "CC 3", "CC 4"),
    "CE": ("CE 1", "CE 2", "CE 3"),
    "CCEC": ("CCEC 1", "CCEC 2", "CCEC 3", "CCEC 4"),
}

DESCRIPTORES_BACH: dict[str, tuple[str, ...]] = {
    "CCL": ("CCL 1", "CCL 2", "CCL 3", "CCL 4", "CCL 5"),
    "CP": ("CP 1", "CP 2", "CP 3"),
    "STEM": ("STEM 1", "STEM 2", "STEM 3", "STEM 4", "STEM 5"),
    "CD": ("CD 1", "CD 2", "CD 3", "CD 4", "CD 5"),
    "CPSAA": (
        "CPSAA 1.1",
        "CPSAA 1.2",
        "CPSAA 2",
        "CPSAA 3.1",
        "CPSAA 3.2",
        "CPSAA 4",
        "CPSAA 5",
    ),
    "CC": ("CC 1", "CC 2", "CC 3", "CC 4"),
    "CE": ("CE 1", "CE 2", "CE 3"),
    "CCEC": (
        "CCEC 1",
        "CCEC 2",
        "CCEC 3.1",
        "CCEC 3.2",
        "CCEC 4.1",
        "CCEC 4.2",
    ),
}

_schema_ready = False


def _join_descriptores(codes: tuple[str, ...] | list[str]) -> str:
    return "\n".join(codes)


def parse_descriptores(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [line.strip() for line in str(raw).splitlines() if line.strip()]


def list_descriptores_operativos(etapa: str) -> list[str]:
    """Descriptores operativos oficiales de la etapa, en orden curricular."""
    stage = (etapa or "").strip().lower()
    source = DESCRIPTORES_BACH if stage == "bach" else DESCRIPTORES_ESO
    out: list[str] = []
    for item in COMPETENCIAS_CLAVE_SEED:
        out.extend(source.get(item["abreviatura"], ()))
    return out


def descriptores_por_competencia(etapa: str) -> dict[str, tuple[str, ...]]:
    """Abreviatura de competencia clave → descriptores operativos de la etapa."""
    stage = (etapa or "").strip().lower()
    source = DESCRIPTORES_BACH if stage == "bach" else DESCRIPTORES_ESO
    return {item["abreviatura"]: source.get(item["abreviatura"], ()) for item in COMPETENCIAS_CLAVE_SEED}


def _enrich(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["descriptores_eso_list"] = parse_descriptores(out.get("descriptores_eso"))
    out["descriptores_bach_list"] = parse_descriptores(out.get("descriptores_bach"))
    return out


def ensure_competencias_clave_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    abreviatura TEXT PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    descriptores_eso TEXT NOT NULL DEFAULT '',
                    descriptores_bach TEXT NOT NULL DEFAULT '',
                    orden SMALLINT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            for i, item in enumerate(COMPETENCIAS_CLAVE_SEED, start=1):
                abrev = item["abreviatura"]
                eso = _join_descriptores(DESCRIPTORES_ESO.get(abrev, ()))
                bach = _join_descriptores(DESCRIPTORES_BACH.get(abrev, ()))
                cur.execute(
                    f"""
                    INSERT INTO {TABLE} (
                        abreviatura, nombre, descriptores_eso,
                        descriptores_bach, orden
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (abreviatura) DO NOTHING
                    """,
                    (abrev, item["nombre"], eso, bach, i),
                )
    _schema_ready = True


def list_competencias_clave() -> list[dict[str, Any]]:
    ensure_competencias_clave_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    abreviatura,
                    nombre,
                    descriptores_eso,
                    descriptores_bach,
                    orden,
                    updated_at
                FROM {TABLE}
                ORDER BY orden, abreviatura
                """
            )
            return [_enrich(dict(r)) for r in cur.fetchall()]


def get_competencia_clave(abreviatura: str) -> dict[str, Any] | None:
    ensure_competencias_clave_schema()
    abrev = (abreviatura or "").strip().upper()
    if not abrev:
        return None
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    abreviatura,
                    nombre,
                    descriptores_eso,
                    descriptores_bach,
                    orden,
                    updated_at
                FROM {TABLE}
                WHERE abreviatura = %s
                """,
                (abrev,),
            )
            row = cur.fetchone()
            return _enrich(dict(row)) if row else None


def update_competencia_clave(
    *,
    abreviatura: str,
    nombre: str,
    descriptores_eso: str,
    descriptores_bach: str,
) -> bool:
    """Actualiza nombre y descriptores. Devuelve False si no existe."""
    ensure_competencias_clave_schema()
    abrev = (abreviatura or "").strip().upper()
    if not abrev:
        return False
    # Normaliza a una línea por descriptor.
    eso = _join_descriptores(parse_descriptores(descriptores_eso))
    bach = _join_descriptores(parse_descriptores(descriptores_bach))
    old = get_competencia_clave(abrev)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET nombre = %s,
                    descriptores_eso = %s,
                    descriptores_bach = %s,
                    updated_at = now()
                WHERE abreviatura = %s
                """,
                ((nombre or "").strip(), eso, bach, abrev),
            )
            ok = cur.rowcount > 0
    if ok and old:
        old_eso = _join_descriptores(parse_descriptores(old.get("descriptores_eso")))
        old_bach = _join_descriptores(parse_descriptores(old.get("descriptores_bach")))
        from db.competencias_materia_variables import rebuild_variables_for_etapa

        if old_eso != eso:
            rebuild_variables_for_etapa("eso")
            from db.competencias_alumno_descriptor import rebuild_alumno_descriptor_etapa

            rebuild_alumno_descriptor_etapa("eso")
        if old_bach != bach:
            rebuild_variables_for_etapa("bach")
            from db.competencias_alumno_descriptor import rebuild_alumno_descriptor_etapa

            rebuild_alumno_descriptor_etapa("bach")
    return ok
