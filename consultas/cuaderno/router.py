"""Rutas HTTP bajo ``/cuaderno``."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from auth import load_user_dep
from config import settings
from context import ctx
from consultas.cuaderno.sections_data import CUADERNO_SECTIONS

router = APIRouter(prefix="/cuaderno", tags=["cuaderno"])

_CUADERNO_PDF = settings.BASE_DIR / "static" / "cuaderno" / "cuaderno-profesor-24-25.pdf"


@router.get("/", response_class=HTMLResponse)
def cuaderno_home(request: Request, user: dict = Depends(load_user_dep)):
    pdf_url = (
        "/static/cuaderno/cuaderno-profesor-24-25.pdf"
        if _CUADERNO_PDF.is_file()
        else None
    )
    return request.app.state.templates.TemplateResponse(
        "cuaderno/index.html",
        ctx(
            request,
            user=user,
            title="Cuaderno del profesor",
            portal_shell_title="Cuaderno del profesor",
            cuaderno_sections=CUADERNO_SECTIONS,
            cuaderno_pdf_url=pdf_url,
        ),
    )
