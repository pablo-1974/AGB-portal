"""Ruta pública de aviso «en obras» para espacios del portal."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from auth import load_user_dep
from context import ctx
from db.portal_espacios import get_espacio

router = APIRouter()


@router.get("/espacios/en-obras/{space_id}", response_class=HTMLResponse)
def espacio_en_obras(
    space_id: str,
    request: Request,
    user: dict = Depends(load_user_dep),
):
    espacio = get_espacio(space_id)
    if not espacio:
        raise HTTPException(status_code=404, detail="Espacio no encontrado")
    return request.app.state.templates.TemplateResponse(
        "espacios_en_obras.html",
        ctx(
            request,
            user=user,
            title="En obras",
            portal_shell_title="En obras",
            espacio_id=space_id,
            espacio_title=espacio["title"],
        ),
    )
