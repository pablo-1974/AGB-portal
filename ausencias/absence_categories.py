"""Catálogo administrativo de ausencias (parte mensual; mismo listado que app legacy)."""

from __future__ import annotations

# tuples (código, descripción corta para UI / parte mensual)
ABSENCE_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("A", "Enfermedad >3 días"),
    ("B", "Matrimonio"),
    ("C", "Embarazo"),
    ("D", "Licencia por estudios"),
    ("E", "Asuntos propios"),
    ("F", "Perfeccionamiento"),
    ("G", "Nacimiento hijo / familiar enfermo"),
    ("H", "Traslado / sindicatos / exámenes"),
    ("I", "Deber inexcusable"),
    ("J", "Consulta médica"),
    ("K", "Enfermedad 1–3 días"),
    ("L", "Moscosos y otros"),
    ("Z", "Actividad del centro"),
)

ALLOWED_ABSENCE_CATEGORY_CODES = frozenset(c for c, _ in ABSENCE_CATEGORIES)

MONTHLY_REPORT_EXCLUDED_CATEGORY = "Z"


def category_excluded_from_monthly_report(category: str | None) -> bool:
    """Categoría Z: catalogada administrativamente pero excluida del parte mensual."""
    return (category or "").strip().upper() == MONTHLY_REPORT_EXCLUDED_CATEGORY


def needs_administrative_cataloging(category: str | None) -> bool:
    """Sin categoría asignada (pendiente de catalogar)."""
    return not (category or "").strip()
