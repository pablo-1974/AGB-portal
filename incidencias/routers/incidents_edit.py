# routers/incidents_edit.py

from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import load_user_dep
from utils.permissions import has_permission
from utils.enums import PERM_EDITAR_INCIDENCIA, GRAVEDADES, ESTADOS_INCIDENCIA
from db.incidents import get_incident_by_id, update_incident, delete_incident
from context import ctx
from db.action_logs import log_incident_action

router = APIRouter()

# =================================================
# Formulario de edición de incidencia (GET)
# =================================================
@router.get("/incidents/edit/{incident_id}", response_class=HTMLResponse)
def edit_incident_view(
    incident_id: int,
    request: Request,
    user: dict = Depends(load_user_dep),
):
    if not has_permission(user, PERM_EDITAR_INCIDENCIA):
        raise HTTPException(status_code=403)

    incident = get_incident_by_id(incident_id)
    if not incident:
        raise HTTPException(status_code=404)

    return request.app.state.templates.TemplateResponse(
        "incidents/edit.html",
        ctx(
            request,
            user=user,
            title="Editar incidencia",
            incident=incident,
            gravedades=GRAVEDADES,
            estados=ESTADOS_INCIDENCIA,
        ),
    )

# =================================================
# Guardar cambios de edición de incidencia (POST)
# =================================================
@router.post("/incidents/edit/{incident_id}")
def edit_incident_submit(
    incident_id: int,
    request: Request,
    user: dict = Depends(load_user_dep),
    grupo: str = Form(...),
    alumno: str = Form(...),
    descripcion: str = Form(...),
    gravedad_inicial: str = Form(...),
    estado: str = Form(...),
):
    if not has_permission(user, PERM_EDITAR_INCIDENCIA):
        raise HTTPException(status_code=403)

    update_incident(
        incident_id=incident_id,
        grupo=grupo,
        alumno=alumno,
        descripcion=descripcion,
        gravedad_inicial=gravedad_inicial,
        estado=estado,
    )
    log_incident_action(
        user_id=user.get("id"),
        action="incident_update",
        entity_id=incident_id,
        detail=f"Incidencia editada: {grupo} · {alumno} · estado {estado}",
    )

    return RedirectResponse("/incidents/list?status=updated", status_code=303)

# =================================================
# Borrar incidencia (POST)
# =================================================
@router.post("/incidents/delete/{incident_id}")
def delete_incident_submit(
    incident_id: int,
    user: dict = Depends(load_user_dep),
):
    if not has_permission(user, PERM_EDITAR_INCIDENCIA):
        raise HTTPException(status_code=403)

    delete_incident(incident_id)
    log_incident_action(
        user_id=user.get("id"),
        action="incident_delete",
        entity_id=incident_id,
        detail="Incidencia eliminada",
    )

    return RedirectResponse(
        "/incidents/list?status=deleted",
        status_code=303,
    )
