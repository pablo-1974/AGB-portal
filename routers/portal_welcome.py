"""Bienvenida obligatoria en el primer acceso al portal."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import load_user_dep
from context import ctx
from db.portal_welcome import accept_portal_welcome, has_accepted_portal_welcome

router = APIRouter()


@router.get("/portal/bienvenida", response_class=HTMLResponse)
def portal_bienvenida(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    if has_accepted_portal_welcome(user_id=int(user["id"])):
        request.session["portal_welcome_ok"] = True
        return RedirectResponse("/portal", status_code=303)

    return request.app.state.templates.TemplateResponse(
        "portal/bienvenida.html",
        ctx(
            request,
            user=user,
            title="Bienvenida",
            portal_shell_title="Bienvenida",
            show_nav=False,
            show_header_logout=False,
        ),
    )


@router.post("/portal/bienvenida", response_class=HTMLResponse)
def portal_bienvenida_aceptar(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    accept_portal_welcome(user_id=int(user["id"]))
    request.session["portal_welcome_ok"] = True
    return RedirectResponse("/portal", status_code=303)
