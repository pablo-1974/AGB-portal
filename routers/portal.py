from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import load_user_dep
from config import settings
from context import ctx
from db.portal_espacios import get_espacios_statuses, portal_card_visible
from db.incidents import count_open_incidents
from utils.enums import ROLE_ADMIN, ROLE_JEFE
from portal.avisos import (
    dismiss_buzon_read_aviso,
    dismiss_moscosos_documentacion_aviso,
    dismiss_publicado_aviso,
    get_portal_avisos_for_user,
)

router = APIRouter()

_PRUEBA_PDF_FILENAME = "2526 Informe Resultados 2ª evaluación.pdf"


@router.get("/portal", response_class=HTMLResponse)
def portal_home(request: Request, user: dict = Depends(load_user_dep)):
    statuses = get_espacios_statuses()
    portal_kpis = None
    if user.get("role") in (ROLE_ADMIN, ROLE_JEFE):
        portal_kpis = {
            "open_incidences": count_open_incidents(),
        }
    return request.app.state.templates.TemplateResponse(
        "portal.html",
        ctx(
            request,
            user=user,
            title="Aplicaciones escolares - Página principal",
            portal_avisos=get_portal_avisos_for_user(user),
            espacios_statuses=statuses,
            portal_card_visible=portal_card_visible,
            portal_kpis=portal_kpis,
        ),
    )


@router.get("/portal/prueba-pdf", response_class=HTMLResponse)
def portal_prueba_pdf(request: Request, user: dict = Depends(load_user_dep)):
    pdf_path = settings.BASE_DIR / "static" / _PRUEBA_PDF_FILENAME
    pdf_url = f"/static/{quote(_PRUEBA_PDF_FILENAME)}"
    return request.app.state.templates.TemplateResponse(
        "portal/prueba_pdf.html",
        ctx(
            request,
            user=user,
            title="Prueba PDF",
            portal_shell_title="Prueba PDF",
            pdf_filename=_PRUEBA_PDF_FILENAME,
            pdf_title=_PRUEBA_PDF_FILENAME,
            pdf_url=pdf_url,
            pdf_available=pdf_path.is_file(),
        ),
    )


@router.post("/portal/avisos/buzones/{buzon_id}/{feedback_id}/ok")
def portal_aviso_buzon_ok(
    buzon_id: str,
    feedback_id: int,
    user: dict = Depends(load_user_dep),
):
    uid = user.get("id")
    if uid is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    dismiss_buzon_read_aviso(
        buzon_id=buzon_id,
        feedback_id=int(feedback_id),
        user_id=int(uid),
    )
    return RedirectResponse("/portal", status_code=303)


@router.post("/portal/avisos/moscosos/documentacion/{reservation_id}/ok")
def portal_aviso_moscosos_documentacion_ok(
    reservation_id: int,
    user: dict = Depends(load_user_dep),
):
    dismiss_moscosos_documentacion_aviso(
        reservation_id=int(reservation_id),
        user=user,
    )
    return RedirectResponse("/portal", status_code=303)


@router.post("/portal/avisos/publicados/{notice_id}/ok")
def portal_aviso_publicado_ok(
    notice_id: int,
    user: dict = Depends(load_user_dep),
):
    uid = user.get("id")
    if uid is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    dismiss_publicado_aviso(notice_id=int(notice_id), user_id=int(uid))
    return RedirectResponse("/portal", status_code=303)
