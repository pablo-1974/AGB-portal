"""Rutas de normas de uso de la app de incidencias."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import load_user_dep
from context import ctx
from db.incidencias_access import accept_incidencias_normas, has_accepted_incidencias_normas
from incidencias.normas_data import NORMAS_INCIDENCIAS_SECTIONS
from utils.enums import PERM_ABRIR_INCIDENCIA
from utils.permissions import has_permission

router = APIRouter()


def _templates(request: Request):
    return request.app.state.templates


def _require_incidencias_app(user: dict) -> None:
    if not has_permission(user, PERM_ABRIR_INCIDENCIA):
        raise HTTPException(status_code=403, detail="Sin permiso")


@router.get("/incidents/normas", response_class=HTMLResponse)
def incidencias_normas(request: Request, user: dict = Depends(load_user_dep)):
    _require_incidencias_app(user)
    accepted = has_accepted_incidencias_normas(user_id=int(user["id"]))
    return _templates(request).TemplateResponse(
        "incidents/normas.html",
        ctx(
            request,
            user=user,
            title="Normas · Incidencias",
            normas_sections=NORMAS_INCIDENCIAS_SECTIONS,
            normas_accepted=accepted,
            normas_pending=not accepted,
        ),
    )


@router.post("/incidents/normas/aceptar")
def incidencias_normas_aceptar(user: dict = Depends(load_user_dep)):
    _require_incidencias_app(user)
    accept_incidencias_normas(user_id=int(user["id"]))
    return RedirectResponse("/dashboard", status_code=303)
