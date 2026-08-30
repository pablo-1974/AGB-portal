"""Agrupación de grupos en columnas para la pantalla En el aula."""

from __future__ import annotations

from db.groups import ensure_groups_schema, list_groups_with_course
from utils.group_stage import extract_course_num, stage_of
from utils.text import normalize_for_sort

GRUPO_COLUMNS: tuple[dict[str, str], ...] = (
    {"id": "eso_1", "title": "1º ESO"},
    {"id": "eso_2", "title": "2º ESO"},
    {"id": "eso_3", "title": "3º ESO"},
    {"id": "eso_4", "title": "4º ESO"},
    {"id": "bach", "title": "Bachillerato"},
    {"id": "fp", "title": "FP"},
)


def grupos_por_columnas() -> list[dict[str, object]]:
    """Seis columnas: 1º–4º ESO, Bachillerato y FP."""
    ensure_groups_schema()
    buckets: dict[str, list[str]] = {col["id"]: [] for col in GRUPO_COLUMNS}

    for g in list_groups_with_course():
        name = (g.get("name") or "").strip()
        if not name:
            continue
        curso = (g.get("curso") or "").strip() or None
        stage = stage_of(grupo=name, curso=curso)
        if not stage:
            continue
        num = extract_course_num(grupo=name, curso=curso, stage=stage)
        if stage == "eso" and num == 1:
            buckets["eso_1"].append(name)
        elif stage == "eso" and num == 2:
            buckets["eso_2"].append(name)
        elif stage == "eso" and num == 3:
            buckets["eso_3"].append(name)
        elif stage == "eso" and num == 4:
            buckets["eso_4"].append(name)
        elif stage == "bachillerato":
            buckets["bach"].append(name)
        elif stage == "fp":
            buckets["fp"].append(name)

    for lst in buckets.values():
        lst.sort(key=normalize_for_sort)

    return [
        {"id": col["id"], "title": col["title"], "grupos": buckets[col["id"]]}
        for col in GRUPO_COLUMNS
    ]
