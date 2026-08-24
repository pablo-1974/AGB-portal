"""Catálogo de documentos de jefatura (PDF en ``static/``)."""

from __future__ import annotations

from typing import TypedDict


class DocumentoJefatura(TypedDict):
    id: str
    title: str
    description: str
    filename: str


# Coloca el PDF en static/<filename> (o ajusta la ruta relativa a static/).
DOCUMENTOS_JEFATURA: tuple[DocumentoJefatura, ...] = (
    {
        "id": "calendario-inicio-curso",
        "title": "Calendario Inicio de Curso",
        "description": "Calendario de inicio de curso (doc. 2627).",
        "filename": "2627 Calendario Inicio de Curso.pdf",
    },
    {
        "id": "evaluacion-lomloe",
        "title": "Evaluación LOMLOE",
        "description": "Documento de evaluación LOMLOE.",
        "filename": "Evaluación LOMLOE.pdf",
    },
)
