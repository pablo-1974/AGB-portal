"""Tipos de mensaje — funcionamiento del portal."""

from __future__ import annotations

TIPO_MAL_FUNCIONAMIENTO = "mal_funcionamiento"
TIPO_SUGERENCIA = "sugerencia"

TIPO_LABELS: dict[str, str] = {
    TIPO_MAL_FUNCIONAMIENTO: "Comunicación de mal funcionamiento",
    TIPO_SUGERENCIA: "Sugerencia de mejora del portal",
}


def is_valid_tipo(raw: str | None) -> bool:
    return (raw or "").strip() in TIPO_LABELS


def tipo_label(raw: str) -> str:
    return TIPO_LABELS.get(raw, raw)
