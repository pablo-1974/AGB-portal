# routers/convivencia_dashboard.py

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse

from utils.time_madrid import today_madrid

from auth import load_user_dep
from context import ctx
from db.school_calendar import get_course_start_iso

from db.incidents import (
    count_incidents,
    count_students_with_incidents,
    count_groups_with_incidents,
)

router = APIRouter()


@router.get("/convivencia/dashboard", response_class=HTMLResponse)
def convivencia_dashboard(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    # Acceso exclusivo para rol convivencia
    if user["role"] != "convivencia":
        raise HTTPException(status_code=403)

    fecha_desde = get_course_start_iso()
    fecha_hasta = today_madrid().isoformat()

    # KPIs (incidencias del curso actual, mismo criterio que el listado por defecto)
    kpis = {
        "total_incidences": count_incidents(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        ),
        "students_with_incidents": count_students_with_incidents(),
        "groups_with_incidents": count_groups_with_incidents(),
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
    }

    return request.app.state.templates.TemplateResponse(
        "convivencia/dashboard.html",
        ctx(
            request,
            user=user,
            title="Dashboard de convivencia",
            kpis=kpis,
        ),
    )
