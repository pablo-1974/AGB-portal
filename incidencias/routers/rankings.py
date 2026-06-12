# routers/rankings.py

from collections import Counter
from datetime import date
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse

from db.incidents import get_incidents
from db.school_calendar import get_course_start_iso
from context import ctx
from auth import load_user_dep
from db.students import get_all_groups

from utils.permissions import has_permission
from utils.enums import (
    PERM_RANKING_ALUMNOS,
    PERM_RANKING_GRUPOS,
    PERM_RANKING_PROFESORES,
)

router = APIRouter()


@router.get("/rankings", response_class=HTMLResponse)
def rankings(
    request: Request,
    mode: str = "alumnos",
    gravedad: str | None = None,
    grupo: str | None = None,
    from_: str | None = None,
    to: str | None = None,
    user=Depends(load_user_dep),
):
    
    # ✅ CONTROL DE PERMISOS
    if mode == "alumnos":
        if not has_permission(user, PERM_RANKING_ALUMNOS):
            raise HTTPException(status_code=403)
    elif mode == "grupos":
        if not has_permission(user, PERM_RANKING_GRUPOS):
            raise HTTPException(status_code=403)
    else:  # profesores
        if not has_permission(user, PERM_RANKING_PROFESORES):
            raise HTTPException(status_code=403)

    """
    Rankings de incidencias.
    """

    fecha_desde = from_ or get_course_start_iso()
    fecha_hasta = to or date.today().isoformat()

    grupos = get_all_groups()

    # ✅ Definir título y columna ANTES del bucle
    if mode == "alumnos":
        titulo = "Ranking de alumnos"
        columna = "Alumno"
    elif mode == "grupos":
        titulo = "Ranking de grupos"
        columna = "Grupo"
    else:
        titulo = "Ranking de profesores"
        columna = "Profesor"

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
                "grupo": alumno_grupo.get(alumno),  # 👈 AQUÍ APARECE EL GRUPO
                "total": total,
            }
            for alumno, total in counter.most_common()
        ]
    else:
        rows = [
            {"nombre": k, "total": v}
            for k, v in counter.most_common()
        ]

    return request.app.state.templates.TemplateResponse(
        "rankings.html",
        ctx(
            request,
            user,
            title=titulo,
            mode=mode,
            columna=columna,
            gravedad=gravedad,
            grupo_sel=grupo,
            grupos=grupos,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            rows=rows,
        ),
    )
