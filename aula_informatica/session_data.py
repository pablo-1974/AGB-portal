"""Estado de sesión, validación y borrador del informe."""

from __future__ import annotations

from typing import Any

from aula_informatica.aulas_data import NUM_PUESTOS
from aula_informatica.students_display import list_alumnos_para_puestos
from db.students import get_student_by_id
from utils.text import normalize_for_sort

SESSION_DRAFT_KEY = "aula_informatica_draft"
SESSION_OK_KEY = "aula_informatica_ok"
SESSION_SENT_KEY = "aula_informatica_sent"

ESTADO_BUEN = "buen_estado"
ESTADO_INCIDENCIAS = "incidencias"
ESTADO_CHOICES: tuple[tuple[str, str], ...] = (
    (ESTADO_BUEN, "Buen estado"),
    (ESTADO_INCIDENCIAS, "Incidencias"),
)
VALID_ESTADOS = frozenset({ESTADO_BUEN, ESTADO_INCIDENCIAS})


def _estado_label(estado: str) -> str:
    for value, label in ESTADO_CHOICES:
        if value == estado:
            return label
    return estado


def parse_puestos_from_form(
    form: Any,
    *,
    allowed_student_ids: set[int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for puesto in range(1, NUM_PUESTOS + 1):
        raw_sid = form.get(f"puesto_{puesto}")
        if not raw_sid:
            continue
        try:
            sid = int(str(raw_sid).strip())
        except (TypeError, ValueError):
            continue
        if sid not in allowed_student_ids:
            continue
        estado = str(form.get(f"estado_{puesto}") or ESTADO_BUEN).strip()
        if estado not in VALID_ESTADOS:
            estado = ESTADO_BUEN
        incidencia = str(form.get(f"incidencia_{puesto}") or "").strip()
        rows.append(
            {
                "puesto": puesto,
                "student_id": sid,
                "estado": estado,
                "incidencia": incidencia,
            }
        )
    return rows


def validate_puestos_rows(
    rows: list[dict[str, Any]],
    *,
    required_student_ids: list[int],
) -> str | None:
    required = set(required_student_ids)
    assigned = [int(r["student_id"]) for r in rows]
    if len(assigned) != len(required):
        return "Debe asignar un puesto a cada alumno seleccionado."
    if set(assigned) != required:
        return "Debe asignar un puesto a cada alumno seleccionado (sin repetir ni omitir)."
    if len(assigned) != len(set(assigned)):
        return "Un alumno no puede ocupar más de un puesto."
    for row in rows:
        if row["estado"] == ESTADO_INCIDENCIAS and not (row.get("incidencia") or "").strip():
            return f"Indique la incidencia del puesto {row['puesto']}."
    return None


def validate_puestos_rows_edit(rows: list[dict[str, Any]]) -> str | None:
    """Edición: permite el mismo alumno en varios puestos (cambios de sitio)."""
    for row in rows:
        if row["estado"] == ESTADO_INCIDENCIAS and not (row.get("incidencia") or "").strip():
            return f"Indique la incidencia del puesto {row['puesto']}."
    return None


def grupos_from_student_ids(student_ids: list[int]) -> list[str]:
    grupos: set[str] = set()
    for sid in student_ids:
        student = get_student_by_id(int(sid))
        if not student:
            continue
        grupo = str(student.get("grupo") or "").strip()
        if grupo:
            grupos.add(grupo)
    return sorted(grupos, key=normalize_for_sort)


def build_draft(
    *,
    aula_id: str,
    session_date: str,
    class_hour: str,
    student_ids: list[int],
    puestos_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    alumnos_map = {int(a["id"]): a for a in list_alumnos_para_puestos(student_ids)}
    puestos: list[dict[str, Any]] = []
    for row in sorted(puestos_rows, key=lambda r: int(r["puesto"])):
        sid = int(row["student_id"])
        alumno = alumnos_map.get(sid)
        if not alumno:
            student = get_student_by_id(sid)
            if not student:
                continue
            grupo = str(student.get("grupo") or "").strip()
            nombre = str(student.get("alumno") or "").strip()
            label = f"{nombre} ({grupo})" if grupo else nombre
            alumno = {"id": sid, "label": label, "grupo": grupo, "alumno": nombre}
        estado = str(row["estado"])
        incidencia = str(row.get("incidencia") or "").strip()
        puestos.append(
            {
                "puesto": int(row["puesto"]),
                "student_id": sid,
                "alumno_label": alumno["label"],
                "grupo": alumno.get("grupo") or "",
                "estado": estado,
                "estado_label": _estado_label(estado),
                "incidencia": incidencia,
            }
        )
    return {
        "aula_id": aula_id,
        "session_date": session_date,
        "class_hour": class_hour,
        "student_ids": list(student_ids),
        "grupos": grupos_from_student_ids(student_ids),
        "puestos": puestos,
        "otras_incidencias": "",
    }


def form_state_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_puesto: dict[int, dict[str, Any]] = {}
    for row in rows:
        by_puesto[int(row["puesto"])] = row
    return {"puestos": by_puesto}
