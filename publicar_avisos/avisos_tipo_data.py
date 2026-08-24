"""Catálogo inicial de avisos tipo (Publicar avisos)."""

from __future__ import annotations

from typing import TypedDict


class AvisoTipo(TypedDict):
    id: str
    title: str
    description: str


AVISOS_TIPO: tuple[AvisoTipo, ...] = (
    {
        "id": "nuevo-alumno",
        "title": "Nuevo alumno",
        "description": "Aviso de alta de un alumno en el centro.",
    },
    {
        "id": "baja-alumno",
        "title": "Baja de un alumno",
        "description": "Aviso de baja de un alumno del centro.",
    },
    {
        "id": "nuevo-profesor",
        "title": "Nuevo profesor",
        "description": "Aviso de incorporación de un profesor.",
    },
)
