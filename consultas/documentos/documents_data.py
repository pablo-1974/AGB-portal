"""Catálogo de documentos institucionales (PDF en ``static/documentos/``)."""

from __future__ import annotations

from typing import TypedDict


class DocumentoInstitucional(TypedDict):
    id: str
    title: str
    description: str
    filename: str | None


# Añade entradas y coloca el PDF en static/documentos/<filename>
DOCUMENTOS_INSTITUCIONALES: tuple[DocumentoInstitucional, ...] = (
    {
        "id": "rri",
        "title": "Reglamento de Régimen Interior",
        "description": "Normativa de convivencia y organización del centro.",
        "filename": "rri.pdf",
    },
    {
        "id": "pai",
        "title": "Proyecto educativo / PAI",
        "description": "Documentación del proyecto educativo del centro.",
        "filename": "pai.pdf",
    },
    {
        "id": "organigrama",
        "title": "Organigrama",
        "description": "Estructura organizativa del centro.",
        "filename": "organigrama.pdf",
    },
    {
        "id": "plan-convivencia",
        "title": "Plan de convivencia",
        "description": "Medidas y protocolos de convivencia escolar.",
        "filename": "plan-convivencia.pdf",
    },
)
