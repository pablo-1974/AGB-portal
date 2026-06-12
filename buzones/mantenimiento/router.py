"""Rutas de la app Mantenimiento."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from buzones.common import rows_for_list
from buzones.deps import (
    require_buzones_staff,
    require_buzones_user,
    require_mantenimiento_marcar,
)
from buzones.mantenimiento import types as mant_types
from context import ctx
from db import mantenimiento_feedback as mant_db
from utils.enums import PERM_BUZONES_MARCAR_LEIDO_MANTENIMIENTO
from utils.permissions import has_permission

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/buzones/mantenimiento", tags=["mantenimiento"])

URL_BASE = "/buzones/mantenimiento"
HEADER_TITLE = "Mantenimiento"
APP_TITLE = "Mantenimiento"
APP_INTRO = (
    "Avisos de mantenimiento del edificio y de los medios informáticos del centro."
)
_MIN_MENSAJE = 10


def _templates(request: Request):
    return request.app.state.templates


def _app_ctx(request: Request, user: dict, **extra):
    return ctx(
        request,
        user=user,
        url_base=URL_BASE,
        buzon_header_title=HEADER_TITLE,
        buzon_title=APP_TITLE,
        buzon_intro=APP_INTRO,
        can_mark_read=has_permission(user, PERM_BUZONES_MARCAR_LEIDO_MANTENIMIENTO),
        **extra,
    )


def _tipos_enviar() -> list[dict]:
    return [
        {
            "id": tid,
            "title": label,
            "href": f"{URL_BASE}/enviar?tipo={tid}",
        }
        for tid, label in mant_types.TIPO_LABELS.items()
    ]


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, user: dict = Depends(require_buzones_user)):
    return _templates(request).TemplateResponse(
        "mantenimiento/dashboard.html",
        _app_ctx(request, user, title=f"{APP_TITLE} · Buzones"),
    )


@router.get("/enviar", response_class=HTMLResponse)
def enviar_get(request: Request, user: dict = Depends(require_buzones_user)):
    tipo = (request.query_params.get("tipo") or "").strip()
    if not mant_types.is_valid_tipo(tipo):
        return _templates(request).TemplateResponse(
            "mantenimiento/enviar_elegir.html",
            _app_ctx(
                request,
                user,
                title=f"Enviar mensaje · {APP_TITLE}",
                tipos=_tipos_enviar(),
            ),
        )
    status = (request.query_params.get("status") or "").strip()
    return _templates(request).TemplateResponse(
        "mantenimiento/enviar.html",
        _app_ctx(
            request,
            user,
            title=f"{mant_types.tipo_label(tipo)} · {APP_TITLE}",
            tipo=tipo,
            tipo_label=mant_types.tipo_label(tipo),
            status=status,
        ),
    )


@router.post("/enviar", response_class=HTMLResponse)
def enviar_post(
    request: Request,
    user: dict = Depends(require_buzones_user),
    tipo: str = Form(...),
    mensaje: str = Form(""),
):
    tipo = (tipo or "").strip()
    if not mant_types.is_valid_tipo(tipo):
        return RedirectResponse(f"{URL_BASE}/enviar", status_code=303)

    text = (mensaje or "").strip()
    if len(text) < _MIN_MENSAJE:
        return RedirectResponse(
            f"{URL_BASE}/enviar?tipo={tipo}&status=short", status_code=303
        )

    user_id = user.get("id")
    if user_id is None:
        return RedirectResponse(
            f"{URL_BASE}/enviar?tipo={tipo}&status=error", status_code=303
        )

    try:
        mant_db.insert_feedback(user_id=int(user_id), tipo=tipo, mensaje=text)
    except Exception:
        _log.exception("Error guardando aviso mantenimiento user=%s", user_id)
        return RedirectResponse(
            f"{URL_BASE}/enviar?tipo={tipo}&status=error", status_code=303
        )

    return RedirectResponse(
        f"{URL_BASE}/enviar?tipo={tipo}&status=ok", status_code=303
    )


@router.get("/mis-mensajes", response_class=HTMLResponse)
def mis_mensajes(request: Request, user: dict = Depends(require_buzones_user)):
    mensajes: list[dict] = []
    user_id = user.get("id")
    if user_id is not None:
        try:
            mensajes = rows_for_list(
                mant_db.list_feedback_for_user(user_id=int(user_id)),
                tipo_labels=mant_types.TIPO_LABELS,
            )
        except Exception:
            _log.exception("Error listando mis avisos mantenimiento")

    return _templates(request).TemplateResponse(
        "mantenimiento/mis_mensajes.html",
        _app_ctx(
            request,
            user,
            title=f"Mis mensajes · {APP_TITLE}",
            mensajes=mensajes,
        ),
    )


@router.get("/listar-mensajes", response_class=HTMLResponse)
def listar_mensajes(request: Request, user: dict = Depends(require_buzones_staff)):
    status = (request.query_params.get("status") or "").strip()
    mensajes: list[dict] = []
    try:
        mensajes = rows_for_list(
            mant_db.list_all_feedback(),
            tipo_labels=mant_types.TIPO_LABELS,
            include_user=True,
        )
    except Exception:
        _log.exception("Error listando avisos mantenimiento")

    unread = [m for m in mensajes if not m["is_read"]]
    read = [m for m in mensajes if m["is_read"]]

    return _templates(request).TemplateResponse(
        "mantenimiento/listar_mensajes.html",
        _app_ctx(
            request,
            user,
            title=f"Listar mensajes · {APP_TITLE}",
            mensajes_unread=unread,
            mensajes_read=read,
            unread_count=len(unread),
            read_count=len(read),
            status=status,
        ),
    )


@router.post("/listar-mensajes/{feedback_id}/leido", response_class=HTMLResponse)
def marcar_leido(
    feedback_id: int,
    user: dict = Depends(require_mantenimiento_marcar),
):
    reader_id = user.get("id")
    if reader_id is None:
        return RedirectResponse(f"{URL_BASE}/listar-mensajes?status=error", status_code=303)
    try:
        mant_db.mark_feedback_read(
            feedback_id=int(feedback_id), reader_user_id=int(reader_id)
        )
    except Exception:
        _log.exception("Error marcando leído mantenimiento id=%s", feedback_id)
        return RedirectResponse(f"{URL_BASE}/listar-mensajes?status=error", status_code=303)
    return RedirectResponse(f"{URL_BASE}/listar-mensajes?status=marked", status_code=303)
