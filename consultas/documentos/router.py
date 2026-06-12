"""Rutas HTTP bajo ``/documentos``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from auth import load_user_dep
from config import settings
from context import ctx
from consultas.documentos.documents_data import DOCUMENTOS_INSTITUCIONALES

router = APIRouter(prefix="/documentos", tags=["documentos"])


def _documentos_for_template() -> list[dict]:
    static_dir = settings.BASE_DIR / "static" / "documentos"
    items: list[dict] = []
    for doc in DOCUMENTOS_INSTITUCIONALES:
        filename = (doc.get("filename") or "").strip() or None
        pdf_url: str | None = None
        available = False
        if filename:
            path = static_dir / filename
            if path.is_file():
                pdf_url = f"/static/documentos/{filename}"
                available = True
        items.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "description": doc["description"],
                "pdf_url": pdf_url,
                "available": available,
                "filename": filename,
            }
        )
    return items


@router.get("/", response_class=HTMLResponse)
def documentos_home(request: Request, user: dict = Depends(load_user_dep)):
    docs = _documentos_for_template()
    return request.app.state.templates.TemplateResponse(
        "documentos/index.html",
        ctx(
            request,
            user=user,
            title="Documentos institucionales",
            portal_shell_title="Documentos institucionales",
            documentos=docs,
            documentos_disponibles=sum(1 for d in docs if d["available"]),
        ),
    )
