# routers/incidents_close.py
"""
FASE 3 · Cierre de incidencias
Vista de gestión (solo ADMIN y JEFE)
"""

from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import load_user_dep
from context import ctx
from db.incidents import (
    get_open_incidents_for_closing,
    close_incident,
)
from db.action_logs import log_incident_action
from utils.enums import GRAVEDADES
from utils.permissions import has_permission
from utils.enums import PERM_CERRAR_INCIDENCIA

router = APIRouter()

# ------------------------------------------------------
# VISTA · COLA DE INCIDENCIAS ABIERTAS
# ------------------------------------------------------

@router.get("/incidents/close", response_class=HTMLResponse)
def incidents_close_view(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    if not has_permission(user, PERM_CERRAR_INCIDENCIA):
        raise HTTPException(status_code=403)

    incidents = get_open_incidents_for_closing()

    return request.app.state.templates.TemplateResponse(
        "incidents/close.html",
        ctx(
            request,
            user=user,
            title="Cerrar incidencias",
            incidents=incidents,
            gravedades=GRAVEDADES,
        ),
    )


# ------------------------------------------------------
# ACCIÓN · CERRAR INCIDENCIA
# ------------------------------------------------------

@router.post("/incidents/close/{incident_id}")
def incidents_close_submit(
    incident_id: int,
    request: Request,
    user: dict = Depends(load_user_dep),
    gravedad_final: str = Form(...),
):
    if not has_permission(user, PERM_CERRAR_INCIDENCIA):
        raise HTTPException(status_code=403)

    # Validación defensiva
    if gravedad_final not in GRAVEDADES:
        raise HTTPException(
            status_code=400,
            detail="Debe seleccionarse una gravedad final válida."
        )

    # ✅ Cierre real de la incidencia
    close_incident(
        incident_id=incident_id,
        gravedad_final=gravedad_final,
        reviewer_id=user["id"],
        reviewer_name=user["name"],
    )
    log_incident_action(
        user_id=user.get("id"),
        action="incident_close",
        entity_id=incident_id,
        detail=f"Incidencia cerrada; gravedad final: {gravedad_final}",
    )

    # ✅ Redirección correcta a la cola
    return RedirectResponse(
        url="/incidents/close",
        status_code=303,
    )
