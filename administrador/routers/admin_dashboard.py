# routers/admin_dashboard.py
"""
Dashboard principal del sistema (Administración / Jefatura).

Acceso controlado por permiso PERM_DASHBOARD_JEFATURA.
Las rutas de PAA y expedientes están en routers/admin_sanciones.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from auth import load_user_dep
from context import ctx
from db.incidents import count_open_incidents, count_total_incidents
from utils.enums import PERM_DASHBOARD_JEFATURA
from utils.permissions import has_permission

router = APIRouter()


def _require_dashboard_access(user):
    if not has_permission(user, PERM_DASHBOARD_JEFATURA):
        raise HTTPException(status_code=403)


@router.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    _require_dashboard_access(user)
    return request.app.state.templates.TemplateResponse(
        "admin/dashboard.html",
        ctx(
            request,
            user=user,
            title="Dashboard de administración",
            kpis={
                "open_incidences": count_open_incidents(),
                "total_incidences": count_total_incidents(),
            },
        ),
    )
