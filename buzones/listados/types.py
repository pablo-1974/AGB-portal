"""Tipos de mensaje — buzón Listados."""

from __future__ import annotations

TIPO_ERROR = "error_listados"
TIPO_SUGERENCIA = "sugerencia_listados"

TIPO_LABELS: dict[str, str] = {
    TIPO_ERROR: "Comunicación de error en listados",
    TIPO_SUGERENCIA: "Sugerencia de mejora en listados",
}


def is_valid_tipo(raw: str | None) -> bool:
    return (raw or "").strip() in TIPO_LABELS


def tipo_label(raw: str) -> str:
    return TIPO_LABELS.get(raw, raw)
