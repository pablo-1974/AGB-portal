# routers/convivencia_dashboard.py

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse

from auth import load_user_dep
from context import ctx

from db.incidents import (
    count_total_incidents,
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

    # KPIs
    kpis = {
        "total_incidences": count_total_incidents(),
        "students_with_incidents": count_students_with_incidents(),
        "groups_with_incidents": count_groups_with_incidents(),
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
