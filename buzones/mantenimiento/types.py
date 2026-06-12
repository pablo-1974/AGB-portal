"""Tipos de mensaje — mantenimiento."""

from __future__ import annotations

TIPO_EDIFICIO = "mantenimiento_edificio"
TIPO_INFORMATICA = "mantenimiento_informatica"

TIPO_LABELS: dict[str, str] = {
    TIPO_EDIFICIO: "Mantenimiento del edificio",
    TIPO_INFORMATICA: "Mantenimiento medios informáticos",
}


def is_valid_tipo(raw: str | None) -> bool:
    return (raw or "").strip() in TIPO_LABELS


def tipo_label(raw: str) -> str:
    return TIPO_LABELS.get(raw, raw)
