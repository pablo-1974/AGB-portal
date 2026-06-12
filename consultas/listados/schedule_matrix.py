"""Matrices de horario para consulta en listados (reutiliza criterios de admin/schedules)."""

from __future__ import annotations

from typing import Any

from ausencias.db import list_schedule_slots


def _schedule_axis_int(slot: dict, key: str) -> int:
    v = slot.get(key)
    if v is None:
        return -1
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def _slot_for_schedule_template(row: dict) -> dict:
    out = dict(row)
    raw = out.get("slot_type")
    if raw is None:
        raw = out.get("type")
    if hasattr(raw, "name"):
        raw = raw.name
    out["schedule_kind"] = str(raw or "").strip().upper()
    return out


def build_teacher_schedule_matrix(*, teacher_id: int) -> list[list[Any]]:
    matrix: list[list[Any]] = [[None for _ in range(5)] for _ in range(7)]
    for slot in list_schedule_slots(teacher_id=teacher_id):
        di = _schedule_axis_int(slot, "day_index")
        hi = _schedule_axis_int(slot, "hour_index")
        if 0 <= di <= 4 and 0 <= hi <= 6:
            matrix[hi][di] = _slot_for_schedule_template(slot)
    return matrix


def template_cell_to_pdf_cell(cell: Any) -> dict | None:
    if cell is None:
        return None
    if isinstance(cell, dict) and cell.get("schedule_kind") == "BLOQUE":
        lines = cell.get("lines") or []
        txt = "<br/>".join(str(x) for x in lines if str(x).strip())
        if not txt:
            return None
        return {"type": "CLASS", "group": "", "room": "", "subject": txt}
    sk = str(cell.get("schedule_kind") or "").upper()
    if sk == "CLASS":
        return {
            "type": "CLASS",
            "group": str(cell.get("group") or ""),
            "room": str(cell.get("room") or ""),
            "subject": str(cell.get("subject") or ""),
        }
    if sk == "GUARD":
        return {"type": "GUARD", "guard_type": str(cell.get("guard_type") or "")}
    if sk == "GUARD_AULA_ALIASES":
        als = cell.get("aliases") or []
        txt = "<br/>".join(str(x) for x in als if str(x).strip())
        if not txt:
            return None
        return {"type": "CLASS", "group": "", "room": "", "subject": txt}
    if sk == "GUARD_RECREO":
        pas = cell.get("pasillo") or []
        pat = cell.get("patio") or []
        p1 = "<br/>".join(str(x) for x in pas if str(x).strip())
        p2 = "<br/>".join(str(x) for x in pat if str(x).strip())
        sep = "<br/>" if p1 and p2 else ""
        subj = (p1 + sep + p2) if (p1 or p2) else ""
        if not subj:
            return None
        return {"type": "CLASS", "group": "", "room": "", "subject": subj}
    return None


def template_matrix_to_pdf_matrix(matrix: list[list[Any]]) -> list[list[dict | None]]:
    return [[template_cell_to_pdf_cell(c) for c in row] for row in matrix]
