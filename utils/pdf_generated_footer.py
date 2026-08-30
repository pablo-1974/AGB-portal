"""Texto de pie común para PDFs generados (listados, horarios, alumnos)."""

from __future__ import annotations

from utils.time_madrid import format_madrid, now_madrid


def pdf_generated_footer_text() -> str:
    """Línea tipo ``*** Generado el DD/MM/YYYY HH:MM ***`` (hora Europe/Madrid)."""
    return f"*** Generado el {format_madrid(now_madrid())} ***"
