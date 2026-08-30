"""Catálogo de aulas de informática del centro."""

from __future__ import annotations

AULAS_INFORMATICA: tuple[dict[str, str], ...] = (
    {
        "id": "a",
        "label": "Aula A (206)",
        "room": "206",
        "name": "INFORMÁTICA A",
        "reservation_room": "Informática A",
    },
    {
        "id": "b",
        "label": "Aula B (210)",
        "room": "210",
        "name": "INFORMÁTICA B",
        "reservation_room": "Informática B",
    },
    {
        "id": "c",
        "label": "Aula C (209)",
        "room": "209",
        "name": "INFORMÁTICA C",
        "reservation_room": "Informática C",
    },
    {
        "id": "multimedia",
        "label": "Aula Multimedia (301)",
        "room": "301",
        "name": "AULA MULTIMEDIA",
        "reservation_room": "Aula Multimedia",
    },
)

_AULA_BY_ID = {a["id"]: a for a in AULAS_INFORMATICA}
_AULA_ID_BY_RESERVATION_ROOM = {
    str(a["reservation_room"]): a["id"] for a in AULAS_INFORMATICA
}

# Horas lectivas (sin recreo) para sesiones en el aula.
CLASS_HOUR_LABELS: tuple[str, ...] = ("1ª", "2ª", "3ª", "4ª", "5ª", "6ª")
VALID_CLASS_HOURS = frozenset(CLASS_HOUR_LABELS)

NUM_PUESTOS = 24


def get_aula(aula_id: str) -> dict[str, str] | None:
    return _AULA_BY_ID.get(str(aula_id or "").strip().lower())


def get_reservation_room(aula_id: str) -> str | None:
    aula = get_aula(aula_id)
    if not aula:
        return None
    room = str(aula.get("reservation_room") or "").strip()
    return room or None


def get_aula_id_from_reservation_room(room: str) -> str | None:
    key = str(room or "").strip()
    if not key:
        return None
    return _AULA_ID_BY_RESERVATION_ROOM.get(key)
