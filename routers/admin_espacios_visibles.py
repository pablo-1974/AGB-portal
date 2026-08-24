"""Administración: visibilidad de espacios del portal."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import load_user_dep
from context import ctx
from db.portal_espacios import (
    PORTAL_ESPACIOS,
    STATUS_OBRAS,
    STATUS_VISIBLE,
    STATUSES,
    get_espacios_statuses,
    save_espacios_statuses,
)
from db.portal_published_notices import create_espacio_disponible_notice
from utils.enums import PERM_ESPACIOS_VISIBLES
from utils.permissions import has_permission

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin_espacios_visibles"])

_EMOJI_PREFIX_RE = re.compile(r"^[^A-Za-zÁÉÍÓÚÜáéíóúüÑñ0-9]+")


def _require_perm(user: dict) -> None:
    if not has_permission(user, PERM_ESPACIOS_VISIBLES):
        raise HTTPException(status_code=403, detail="Sin permiso")


def _espacio_nombre_aviso(title: str) -> str:
    t = (title or "").strip()
    return _EMOJI_PREFIX_RE.sub("", t).strip() or t


def _espacios_por_seccion() -> list[tuple[str, list[dict[str, str]]]]:
    sections: list[tuple[str, list[dict[str, str]]]] = []
    by_name: dict[str, list[dict[str, str]]] = {}
    for e in PORTAL_ESPACIOS:
        sec = e["section"]
        if sec not in by_name:
            by_name[sec] = []
            sections.append((sec, by_name[sec]))
        by_name[sec].append(e)
    return sections


@router.get("/admin/espacios-visibles", response_class=HTMLResponse)
def espacios_visibles_page(request: Request, user: dict = Depends(load_user_dep)):
    _require_perm(user)
    statuses = get_espacios_statuses(use_cache=False)
    avisos_n = 0
    raw_avisos = request.query_params.get("avisos")
    if raw_avisos and str(raw_avisos).isdigit():
        avisos_n = int(raw_avisos)
    return request.app.state.templates.TemplateResponse(
        "admin/espacios_visibles.html",
        ctx(
            request,
            user=user,
            title="Espacios visibles",
            portal_shell_title="Espacios visibles",
            espacios_por_seccion=_espacios_por_seccion(),
            espacios_statuses=statuses,
            saved=request.query_params.get("saved") == "1",
            avisos_publicados=avisos_n,
        ),
    )


@router.post("/admin/espacios-visibles")
async def espacios_visibles_save(
    request: Request, user: dict = Depends(load_user_dep)
):
    _require_perm(user)
    form = await request.form()
    updates: dict[str, str] = {}
    for espacio in PORTAL_ESPACIOS:
        sid = espacio["id"]
        raw = form.get(f"status_{sid}")
        if raw is None:
            continue
        st = str(raw).strip()
        if st in STATUSES:
            updates[sid] = st

    transitions = save_espacios_statuses(updates)
    logger.info(
        "espacios-visibles: updates=%s transitions=%s",
        updates,
        transitions,
    )

    by_id = {e["id"]: e for e in PORTAL_ESPACIOS}
    avisos_n = 0
    for sid, old_st, new_st in transitions:
        if old_st != STATUS_OBRAS or new_st != STATUS_VISIBLE:
            continue
        espacio = by_id.get(sid)
        if not espacio:
            continue
        nombre = _espacio_nombre_aviso(espacio["title"])
        try:
            notice_id = create_espacio_disponible_notice(
                created_by=user.get("id"),
                app_nombre=nombre,
            )
            avisos_n += 1
            logger.info(
                "espacios-visibles: aviso id=%s para %s (%s)",
                notice_id,
                sid,
                nombre,
            )
        except Exception:
            logger.exception(
                "espacios-visibles: fallo al publicar aviso para %s", sid
            )

    q = urlencode({"saved": "1", "avisos": str(avisos_n)})
    return RedirectResponse(f"/admin/espacios-visibles?{q}", status_code=303)
