from __future__ import annotations

from datetime import date

from utils.time_madrid import today_madrid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from auth import load_user_dep
from context import ctx
from db.groups import list_groups_with_course
from db.incidents import get_serious_incident_counts_by_student
from db.school_calendar import get_course_start_iso
from utils.permissions import has_permission
from utils.enums import PERM_CONTADORES_CONVIVENCIA

router = APIRouter()


def _empty_matrix() -> dict:
    return {"M": 0, "V": 0}


def _build_rows(counter_map: dict[str, dict[str, int]], cursos: list[str]) -> tuple[list[dict], dict[str, int]]:
    rows: list[dict] = []
    total_m = 0
    total_v = 0
    for curso in cursos:
        row = counter_map.get(curso, _empty_matrix())
        m = int(row.get("M", 0))
        v = int(row.get("V", 0))
        rows.append({"curso": curso, "M": m, "V": v})
        total_m += m
        total_v += v
    return rows, {"M": total_m, "V": total_v}


@router.get("/counters", response_class=HTMLResponse)
def convivencia_counters(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    if not has_permission(user, PERM_CONTADORES_CONVIVENCIA):
        raise HTTPException(status_code=403)

    qp = request.query_params
    fecha_desde = qp.get("fecha_desde") or get_course_start_iso()
    fecha_hasta = qp.get("fecha_hasta") or today_madrid().isoformat()

    rows = get_serious_incident_counts_by_student(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )

    item1: dict[str, dict[str, int]] = {}
    item2: dict[str, dict[str, int]] = {}
    item3: dict[str, dict[str, int]] = {}
    ordered_courses: list[str] = []
    seen_courses: set[str] = set()

    for g in list_groups_with_course():
        curso = (str(g.get("curso") or "").strip() or "Sin curso")
        if curso not in seen_courses:
            seen_courses.add(curso)
            ordered_courses.append(curso)

    for r in rows:
        sexo = (r.get("sexo") or "").strip().upper()
        if sexo not in {"M", "V"}:
            continue
        curso = (r.get("curso") or "Sin curso").strip() or "Sin curso"
        if curso not in seen_courses:
            seen_courses.add(curso)
            ordered_courses.append(curso)
        cnt = int(r.get("graves_count") or 0)
        if cnt >= 1:
            item1.setdefault(curso, _empty_matrix())[sexo] += 1
        if cnt >= 5:
            item2.setdefault(curso, _empty_matrix())[sexo] += 1
        if cnt >= 10:
            item3.setdefault(curso, _empty_matrix())[sexo] += 1

    item1_rows, item1_totals = _build_rows(item1, ordered_courses)
    item2_rows, item2_totals = _build_rows(item2, ordered_courses)
    item3_rows, item3_totals = _build_rows(item3, ordered_courses)

    return request.app.state.templates.TemplateResponse(
        "counters/index.html",
        ctx(
            request,
            user=user,
            title="Contadores de Convivencia",
            filters={"fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta},
            item1_rows=item1_rows,
            item1_totals=item1_totals,
            item2_rows=item2_rows,
            item2_totals=item2_totals,
            item3_rows=item3_rows,
            item3_totals=item3_totals,
        ),
    )
