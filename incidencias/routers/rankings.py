# routers/rankings.py

from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from auth import load_user_dep
from context import ctx
from db.incidents import get_incidents
from db.sanciones_ranking import ranking_dias_sancion
from db.school_calendar import get_course_start_iso
from db.students import get_all_groups
from utils.enums import (
    PERM_RANKING_ALUMNOS,
    PERM_RANKING_GRUPOS,
    PERM_RANKING_PROFESORES,
)
from utils.permissions import has_permission

router = APIRouter()

_METRICS = frozenset({"incidencias", "sanciones"})


def _normalize_metric(raw: str | None, *, mode: str) -> str:
    m = (raw or "incidencias").strip().lower()
    if mode == "profesores":
        return "incidencias"
    return m if m in _METRICS else "incidencias"


@router.get("/rankings", response_class=HTMLResponse)
def rankings(
    request: Request,
    mode: str = "alumnos",
    metric: str | None = None,
    gravedad: str | None = None,
    grupo: str | None = None,
    from_: str | None = None,
    to: str | None = None,
    user=Depends(load_user_dep),
):
    if mode == "alumnos":
        if not has_permission(user, PERM_RANKING_ALUMNOS):
            raise HTTPException(status_code=403)
    elif mode == "grupos":
        if not has_permission(user, PERM_RANKING_GRUPOS):
            raise HTTPException(status_code=403)
    else:
        mode = "profesores"
        if not has_permission(user, PERM_RANKING_PROFESORES):
            raise HTTPException(status_code=403)

    metric_n = _normalize_metric(metric, mode=mode)
    fecha_desde = from_ or get_course_start_iso()
    fecha_hasta = to or date.today().isoformat()
    grupos = get_all_groups()

    if mode == "alumnos":
        titulo = (
            "Ranking de alumnos · Días de sanción"
            if metric_n == "sanciones"
            else "Ranking de alumnos · Partes de incidencias"
        )
        columna = "Alumno"
    elif mode == "grupos":
        titulo = (
            "Ranking de grupos · Días de sanción"
            if metric_n == "sanciones"
            else "Ranking de grupos · Partes de incidencias"
        )
        columna = "Grupo"
    else:
        titulo = "Ranking de profesores"
        columna = "Profesor"

    if metric_n == "sanciones":
        rows = ranking_dias_sancion(mode=mode, grupo=grupo)
        col_total = "Días de sanción"
    else:
        rows_raw = get_incidents(
            mode="all",
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
        counter = Counter()
        alumno_grupo = {}

        for r in rows_raw:
            gravedad_real = r["gravedad_final"] or r["gravedad_inicial"]
            if gravedad and gravedad_real != gravedad:
                continue

            if mode == "alumnos":
                if grupo and r["grupo"] != grupo:
                    continue
                key = r["alumno"]
                alumno_grupo[key] = r["grupo"]
            elif mode == "grupos":
                key = r["grupo"]
            else:
                key = r["teacher_name"]

            if key:
                counter[key] += 1

        if mode == "alumnos":
            rows = [
                {
                    "nombre": alumno,
                    "grupo": alumno_grupo.get(alumno),
                    "total": total,
                }
                for alumno, total in counter.most_common()
            ]
        else:
            rows = [{"nombre": k, "total": v} for k, v in counter.most_common()]
        col_total = "Incidencias"

    return request.app.state.templates.TemplateResponse(
        "rankings.html",
        ctx(
            request,
            user,
            title=titulo,
            mode=mode,
            metric=metric_n,
            columna=columna,
            col_total=col_total,
            gravedad=gravedad,
            grupo_sel=grupo,
            grupos=grupos,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            rows=rows,
        ),
    )
