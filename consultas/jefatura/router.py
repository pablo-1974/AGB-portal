"""Rutas HTTP bajo ``/documentos-jefatura``."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import load_user_dep
from config import settings
from context import ctx
from consultas.jefatura.documents_data import DOCUMENTOS_JEFATURA

router = APIRouter(prefix="/documentos-jefatura", tags=["documentos-jefatura"])


def _docs_for_template() -> list[dict]:
    static_dir = settings.BASE_DIR / "static"
    items: list[dict] = []
    for doc in DOCUMENTOS_JEFATURA:
        filename = (doc.get("filename") or "").strip()
        path = static_dir / filename if filename else None
        available = bool(path and path.is_file())
        pdf_url = f"/static/{quote(filename)}" if available else None
        items.append(
            {
                "id": doc["id"],
                "title": doc["title"],
                "description": doc["description"],
                "filename": filename,
                "pdf_url": pdf_url,
                "available": available,
            }
        )
    return items


def _pick_doc(docs: list[dict], doc_id: str | None) -> dict | None:
    if not docs:
        return None
    if doc_id:
        for d in docs:
            if d["id"] == doc_id:
                return d
    # Prefer first available PDF
    for d in docs:
        if d["available"]:
            return d
    return docs[0]


@router.get("/", response_class=HTMLResponse)
def jefatura_home(
    request: Request,
    user: dict = Depends(load_user_dep),
    doc: str | None = None,
):
    docs = _docs_for_template()
    selected = _pick_doc(docs, (doc or "").strip() or None)
    return request.app.state.templates.TemplateResponse(
        "jefatura/index.html",
        ctx(
            request,
            user=user,
            title="Documentos Jefatura",
            portal_shell_title="Documentos Jefatura",
            documentos=docs,
            selected=selected,
        ),
    )


@router.get("/{doc_id}", response_class=HTMLResponse)
def jefatura_doc(
    request: Request,
    doc_id: str,
    user: dict = Depends(load_user_dep),
):
    return RedirectResponse(
        f"/documentos-jefatura/?doc={quote(doc_id)}",
        status_code=303,
    )
