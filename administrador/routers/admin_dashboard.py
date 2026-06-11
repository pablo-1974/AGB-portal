# routers/admin_dashboard.py
"""
Dashboard principal del sistema (Administración / Jefatura).

Acceso controlado por permiso PERM_DASHBOARD_JEFATURA.
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse

from auth import load_user_dep
from context import ctx
from db.incidents import (
    count_open_incidents,
    count_total_incidents,
)

from utils.permissions import has_permission
from utils.enums import PERM_DASHBOARD_JEFATURA

router = APIRouter()


# ----------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------

def _require_dashboard_access(user):
    if not has_permission(user, PERM_DASHBOARD_JEFATURA):
        raise HTTPException(status_code=403)


# ----------------------------------------------------------------------
# DASHBOARD ADMIN
# ----------------------------------------------------------------------

@router.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    """
    Dashboard principal del administrador.
    """
    _require_dashboard_access(user)


    # KPI PRINCIPAL
    open_incidences = count_open_incidents()
    total_incidences = count_total_incidents()


    return request.app.state.templates.TemplateResponse(
        "admin/dashboard.html",
        ctx(
            request,
            user=user,
            title="Dashboard de administración",
            kpis={
                "open_incidences": open_incidences,
                "total_incidences": total_incidences,
            },
        ),
    )
