"""Texto seguro para Paragraph de ReportLab (mini-HTML)."""

from __future__ import annotations

from xml.sax.saxutils import escape


def pdf_markup(value: object) -> str:
    """Escapa ``&``, ``<``, etc. para evitar fallos al generar PDF."""
    return escape(str(value if value is not None else ""))
