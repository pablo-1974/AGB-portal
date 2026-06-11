"""Administración: asignaturas matriculadas (importación Excel)."""

from __future__ import annotations

import io
import logging
from urllib.parse import quote

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from auth import load_user_dep
from context import ctx
from db.enrolled_subjects import (
    EXCEL_HEADERS,
    FIELD_NAMES,
    get_latest_import,
    list_all_rows,
    list_preview_rows,
    parse_workbook_rows,
    replace_import,
)
from utils.enums import PERM_ASIGNATURAS_MATRICULADAS
from utils.permissions import has_permission

router = APIRouter(
    prefix="/admin/asignaturas-matriculadas",
    tags=["admin_enrolled_subjects"],
)

_log = logging.getLogger(__name__)


def _require_perm(user: dict) -> None:
    if not has_permission(user, PERM_ASIGNATURAS_MATRICULADAS):
        raise HTTPException(status_code=403)


def _import_redirect(status: str, *, msg: str | None = None) -> RedirectResponse:
    qs = f"status={status}"
    if msg:
        qs += f"&msg={quote(msg)}"
    return RedirectResponse(f"/admin/asignaturas-matriculadas?{qs}", status_code=303)


def _load_uploaded_workbook(file: UploadFile):
    """Lee el Excel subido en memoria (más fiable que pasar el stream directo)."""
    raw = file.file.read()
    if not raw:
        raise ValueError("Archivo vacío")
    if raw[:2] != b"PK":
        raise ValueError("No es un .xlsx válido (formato ZIP/OpenXML)")
    return openpyxl.load_workbook(io.BytesIO(raw), data_only=True)


@router.get("/", response_class=HTMLResponse)
def admin_enrolled_subjects(request: Request, user: dict = Depends(load_user_dep)):
    _require_perm(user)
    latest = get_latest_import()
    preview = list_preview_rows(limit=50)
    return request.app.state.templates.TemplateResponse(
        "admin/asignaturas_matriculadas.html",
        ctx(
            request,
            user=user,
            title="Asignaturas matriculadas",
            latest_import=latest,
            preview_rows=preview,
            column_labels=EXCEL_HEADERS,
            column_fields=FIELD_NAMES,
        ),
    )


@router.post("/import")
def admin_enrolled_subjects_import(
    user: dict = Depends(load_user_dep),
    file: UploadFile = File(...),
):
    _require_perm(user)

    filename = (file.filename or "").strip().lower()
    if filename and not filename.endswith((".xlsx", ".xlsm")):
        return _import_redirect("error", msg="Use un archivo Excel .xlsx")

    try:
        wb = _load_uploaded_workbook(file)
        idx_to_field, rows = parse_workbook_rows(wb)
    except ValueError as exc:
        _log.warning("Import asignaturas matriculadas rechazado: %s", exc)
        return _import_redirect("error", msg=str(exc))
    except Exception:
        _log.exception("Import asignaturas matriculadas: fallo al leer Excel")
        return _import_redirect(
            "error",
            msg="No se pudo leer el Excel. Compruebe que es .xlsx (no .xls) y no está dañado.",
        )

    if "alumno" not in idx_to_field.values():
        return _import_redirect(
            "bad_headers",
            msg="Falta la columna ALUMNO en las primeras filas del archivo.",
        )

    if not rows:
        return _import_redirect(
            "empty",
            msg="No hay filas con ALUMNO rellenado bajo la cabecera.",
        )

    try:
        replace_import(
            imported_by=user.get("id"),
            filename=file.filename,
            rows=rows,
        )
    except Exception:
        _log.exception("Import asignaturas matriculadas: fallo al guardar en BD")
        return _import_redirect("error", msg="Error al guardar en la base de datos")

    return RedirectResponse(
        f"/admin/asignaturas-matriculadas?status=imported&rows={len(rows)}",
        status_code=303,
    )


@router.get("/export")
def admin_enrolled_subjects_export(user: dict = Depends(load_user_dep)):
    _require_perm(user)

    rows = list_all_rows()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Asignaturas"
    ws.append(list(EXCEL_HEADERS))
    for row in rows:
        ws.append([row.get(field) for field in FIELD_NAMES])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    return Response(
        stream.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="asignaturas-matriculadas.xlsx"'
        },
    )
