from __future__ import annotations

import io

from utils.local_deps import ensure_local_deps

ensure_local_deps()
try:
    import openpyxl
except ImportError:
    openpyxl = None  # type: ignore[assignment]
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from auth import load_user_dep
from context import ctx
from db.departamentos import (
    get_departamentos_meta,
    list_departamentos,
    miembros_por_departamento,
    parse_departamentos_workbook,
    replace_departamentos,
    update_departamento_jefe,
)
from utils.enums import PERM_GESTION_DEPARTAMENTOS
from utils.permissions import has_permission

router = APIRouter(prefix="/admin/departamentos", tags=["admin_departamentos"])


def _templates(request: Request):
    return request.app.state.templates


def _require_perm(user: dict) -> None:
    if not has_permission(user, PERM_GESTION_DEPARTAMENTOS):
        raise HTTPException(status_code=403)


@router.get("/", response_class=HTMLResponse)
def admin_departamentos_page(request: Request, user: dict = Depends(load_user_dep)):
    _require_perm(user)
    departamentos = list_departamentos()
    return _templates(request).TemplateResponse(
        "admin/departamentos.html",
        ctx(
            request,
            user=user,
            title="Gestión de departamentos",
            departamentos=departamentos,
            miembros_por_abrev=miembros_por_departamento(departamentos),
            meta=get_departamentos_meta(),
        ),
    )


@router.post("/jefe")
def admin_departamentos_set_jefe(
    user: dict = Depends(load_user_dep),
    abreviatura: str = Form(...),
    jefe: str = Form(""),
):
    _require_perm(user)
    ok = update_departamento_jefe(abreviatura, jefe)
    if not ok:
        return RedirectResponse("/admin/departamentos/?status=jefe_error", status_code=303)
    return RedirectResponse("/admin/departamentos/?status=jefe_saved", status_code=303)


@router.post("/import")
def admin_departamentos_import(
    user: dict = Depends(load_user_dep),
    file: UploadFile = File(...),
):
    _require_perm(user)
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        return RedirectResponse("/admin/departamentos/?status=error", status_code=303)
    try:
        wb = openpyxl.load_workbook(file.file)
        rows = parse_departamentos_workbook(wb)
        if not rows:
            return RedirectResponse("/admin/departamentos/?status=error", status_code=303)
        inserted, skipped = replace_departamentos(rows)
    except Exception:
        return RedirectResponse("/admin/departamentos/?status=error", status_code=303)
    return RedirectResponse(
        f"/admin/departamentos/?status=imported&inserted={inserted}&skipped={skipped}",
        status_code=303,
    )


@router.get("/export")
def admin_departamentos_export(user: dict = Depends(load_user_dep)):
    _require_perm(user)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Departamentos"
    ws.append(["Departamento", "abreviatura", "Jefe"])
    for row in list_departamentos():
        ws.append(
            [
                row.get("departamento") or "",
                row.get("abreviatura") or "",
                row.get("jefe") or "",
            ]
        )
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return Response(
        stream.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=departamentos.xlsx"},
    )
