"""Texto de pie común para PDFs generados (listados, horarios, alumnos)."""

from __future__ import annotations

from datetime import datetime


def pdf_generated_footer_text() -> str:
    """Línea tipo ``*** Generado el DD/MM/YYYY HH:MM ***`` (hora local del servidor)."""
    return f"*** Generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} ***"
