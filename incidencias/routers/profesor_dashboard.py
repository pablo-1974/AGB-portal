# routers/profesor_dashboard.py

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse

from auth import load_user_dep
from context import ctx

from db.incidents import count_own_incidents

router = APIRouter()


@router.get("/profesor/dashboard", response_class=HTMLResponse)
def profesor_dashboard(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    if user["role"] not in ("profesor", "orientador", "extraescolares"):
        raise HTTPException(status_code=403)

    kpis = {
        "own_incidences": count_own_incidents(user["id"]),
    }

    return request.app.state.templates.TemplateResponse(
        "profesor/dashboard.html",
        ctx(
            request,
            user=user,
            title="Mi panel de incidencias",
            kpis=kpis,
        ),
    )
