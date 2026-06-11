"""Administración: catálogo curso de asignatura (importación Excel)."""

from __future__ import annotations

import io
import logging
from urllib.parse import quote

import openpyxl
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from auth import load_user_dep
from context import ctx
from db.enrolled_subject_catalog import (
    CATALOG_ETAPA_EXPORT_LABELS,
    CATALOG_EXCEL_HEADERS,
    CATALOG_FIELD_NAMES,
    get_catalog_meta,
    list_catalog_for_export,
    list_catalog_preview,
    normalize_catalog_etapa,
    parse_catalog_workbook_rows,
    replace_subject_catalog,
)
from utils.enums import PERM_ASIGNATURAS_MATRICULADAS
from utils.permissions import has_permission

router = APIRouter(
    prefix="/admin/catalogo-asignaturas",
    tags=["admin_subject_catalog"],
)

_log = logging.getLogger(__name__)


def _require_perm(user: dict) -> None:
    if not has_permission(user, PERM_ASIGNATURAS_MATRICULADAS):
        raise HTTPException(status_code=403)


def _redirect(status: str, *, msg: str | None = None, **extra: str) -> RedirectResponse:
    parts = [f"status={status}"]
    if msg:
        parts.append(f"msg={quote(msg)}")
    for key, value in extra.items():
        parts.append(f"{key}={quote(str(value))}")
    return RedirectResponse(f"/admin/catalogo-asignaturas/?{'&'.join(parts)}", status_code=303)


def _load_workbook(file: UploadFile):
    raw = file.file.read()
    if not raw:
        raise ValueError("Archivo vacío")
    if raw[:2] != b"PK":
        raise ValueError("No es un .xlsx válido")
    return openpyxl.load_workbook(io.BytesIO(raw), data_only=True)


@router.get("/", response_class=HTMLResponse)
def admin_subject_catalog_page(request: Request, user: dict = Depends(load_user_dep)):
    _require_perm(user)
    meta = get_catalog_meta()
    preview = list_catalog_preview(limit=80)
    return request.app.state.templates.TemplateResponse(
        "admin/catalogo_asignaturas.html",
        ctx(
            request,
            user=user,
            title="Catálogo asignaturas (curso asignatura)",
            catalog_meta=meta,
            preview_rows=preview,
            column_labels=CATALOG_EXCEL_HEADERS,
            column_fields=CATALOG_FIELD_NAMES,
        ),
    )


@router.post("/import")
def admin_subject_catalog_import(
    user: dict = Depends(load_user_dep),
    file: UploadFile = File(...),
):
    _require_perm(user)
    try:
        wb = _load_workbook(file)
    except ValueError as exc:
        _log.warning("Import catálogo asignaturas rechazado: %s", exc)
        return _redirect("error", msg=str(exc))
    except Exception:
        _log.exception("Import catálogo: fallo al leer Excel")
        return _redirect("error", msg="No se pudo leer el archivo Excel.")

    idx_to_field, rows = parse_catalog_workbook_rows(wb)
    if "materia_abrev" not in idx_to_field.values() or "curso_asign" not in idx_to_field.values():
        return _redirect(
            "bad_headers",
            msg="Faltan columnas obligatorias: MATERIA (abrev.) y CURSO_ASIGN.",
        )
    if not rows:
        return _redirect("empty", msg="No hay filas válidas en el Excel.")

    try:
        inserted, skipped = replace_subject_catalog(rows)
    except Exception:
        _log.exception("Import catálogo: fallo al guardar en BD")
        return _redirect("error", msg="Error al guardar el catálogo en la base de datos.")

    return _redirect("imported", rows=str(inserted), skipped=str(skipped))


@router.get("/export")
def admin_subject_catalog_export(user: dict = Depends(load_user_dep)):
    _require_perm(user)
    rows = list_catalog_for_export()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Catalogo"
    ws.append(list(CATALOG_EXCEL_HEADERS))
    for r in rows:
        etapa_key = normalize_catalog_etapa(r.get("etapa")) or ""
        ws.append(
            [
                r.get("materia_abrev") or "",
                r.get("materia") or "",
                r.get("estudio") or "",
                "",
                r.get("curso_asignatura"),
                CATALOG_ETAPA_EXPORT_LABELS.get(etapa_key, r.get("etapa") or ""),
            ]
        )
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="catalogo-asignaturas.xlsx"'
        },
    )
