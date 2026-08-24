"""Administración: asignaturas matriculadas (importación Excel)."""

from __future__ import annotations

import io
import logging
from urllib.parse import quote, urlencode

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
from db.enrolled_subjects import (
    EXCEL_HEADERS,
    FIELD_NAMES,
    add_enrolled_subject_for_alumno,
    count_preview_rows,
    delete_enrolled_subject_row,
    get_latest_import,
    list_all_rows,
    list_enrolled_filter_alumnos,
    list_enrolled_filter_grupos,
    list_materias_picker_options,
    list_preview_rows,
    parse_workbook_rows,
    replace_import,
    resolve_alumno_etapa_curso,
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


def _alumno_redirect(
    *,
    grupo: str | None = None,
    alumno: str | None = None,
    status: str | None = None,
    msg: str | None = None,
) -> RedirectResponse:
    params: dict[str, str] = {}
    if grupo:
        params["grupo"] = grupo
    if alumno:
        params["alumno"] = alumno
    if status:
        params["status"] = status
    if msg:
        params["msg"] = msg
    qs = urlencode(params)
    url = "/admin/asignaturas-matriculadas/"
    if qs:
        url = f"{url}?{qs}"
    return RedirectResponse(url, status_code=303)


def _load_uploaded_workbook(file: UploadFile):
    """Lee el Excel subido en memoria (más fiable que pasar el stream directo)."""
    raw = file.file.read()
    if not raw:
        raise ValueError("Archivo vacío")
    if raw[:2] != b"PK":
        raise ValueError("No es un .xlsx válido (formato ZIP/OpenXML)")
    return openpyxl.load_workbook(io.BytesIO(raw), data_only=True)


_PREVIEW_PAGE_SIZE = 50


def _preview_page_url(
    *,
    page: int,
    grupo: str = "",
    alumno: str = "",
) -> str:
    params: dict[str, str] = {}
    if grupo:
        params["grupo"] = grupo
    if alumno:
        params["alumno"] = alumno
    if page > 1:
        params["page"] = str(page)
    qs = urlencode(params)
    return f"/admin/asignaturas-matriculadas/?{qs}" if qs else "/admin/asignaturas-matriculadas/"


@router.get("/", response_class=HTMLResponse)
def admin_enrolled_subjects(
    request: Request,
    user: dict = Depends(load_user_dep),
    grupo: str | None = None,
    alumno: str | None = None,
    page: int = 1,
):
    _require_perm(user)
    latest = get_latest_import()
    selected_grupo = (grupo or "").strip()
    selected_alumno = (alumno or "").strip()
    try:
        page_n = max(1, int(page))
    except (TypeError, ValueError):
        page_n = 1

    total_rows = count_preview_rows(
        grupo=selected_grupo or None,
        alumno=selected_alumno or None,
    )
    total_pages = max(1, (total_rows + _PREVIEW_PAGE_SIZE - 1) // _PREVIEW_PAGE_SIZE) if total_rows else 1
    if page_n > total_pages:
        page_n = total_pages
    offset = (page_n - 1) * _PREVIEW_PAGE_SIZE

    if selected_alumno:
        preview = list_preview_rows(
            limit=None,
            grupo=selected_grupo or None,
            alumno=selected_alumno,
        )
        preview_from = 1 if preview else 0
        preview_to = len(preview)
        show_pagination = False
        prev_page_url = None
        next_page_url = None
    else:
        preview = list_preview_rows(
            limit=_PREVIEW_PAGE_SIZE,
            offset=offset,
            grupo=selected_grupo or None,
            alumno=None,
        )
        preview_from = offset + 1 if preview else 0
        preview_to = offset + len(preview)
        show_pagination = total_rows > _PREVIEW_PAGE_SIZE
        prev_page_url = (
            _preview_page_url(page=page_n - 1, grupo=selected_grupo, alumno="")
            if page_n > 1
            else None
        )
        next_page_url = (
            _preview_page_url(page=page_n + 1, grupo=selected_grupo, alumno="")
            if page_n < total_pages
            else None
        )

    filter_grupos = list_enrolled_filter_grupos()
    filter_alumnos = list_enrolled_filter_alumnos(
        grupo=selected_grupo or None,
    )
    if selected_alumno and selected_alumno not in filter_alumnos:
        filter_alumnos = sorted(
            [*filter_alumnos, selected_alumno],
            key=lambda s: s.casefold(),
        )
    filtered = bool(selected_grupo or selected_alumno)
    can_edit_alumno = bool(selected_alumno)
    add_materia_options = (
        list_materias_picker_options(alumno=selected_alumno) if can_edit_alumno else []
    )
    alumno_ctx = (
        resolve_alumno_etapa_curso(selected_alumno) if can_edit_alumno else {}
    )
    add_materias_hint = ""
    if can_edit_alumno and not add_materia_options:
        if not alumno_ctx.get("etapa") or not alumno_ctx.get("curso_num"):
            add_materias_hint = (
                "No se pudo determinar la etapa o el curso del alumno "
                f"(estudio={alumno_ctx.get('estudio')!r}, "
                f"curso={alumno_ctx.get('curso')!r}, "
                f"grupo={alumno_ctx.get('nombre_grupo')!r}). "
                "Revise esos campos en la matrícula o el curso del grupo en Administración."
            )
        else:
            add_materias_hint = (
                f"No hay materias del catálogo para {alumno_ctx.get('etapa')} "
                f"{alumno_ctx.get('curso_num')}º (o el alumno ya las tiene todas). "
                "Compruebe que el catálogo de asignaturas está importado."
            )
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
            filter_grupos=filter_grupos,
            filter_alumnos=filter_alumnos,
            selected_grupo=selected_grupo,
            selected_alumno=selected_alumno,
            preview_filtered=filtered,
            can_edit_alumno=can_edit_alumno,
            add_materia_options=add_materia_options,
            add_materias_hint=add_materias_hint,
            preview_page=page_n,
            preview_total_pages=total_pages,
            preview_total_rows=total_rows,
            preview_from=preview_from,
            preview_to=preview_to,
            show_preview_pagination=show_pagination,
            preview_prev_url=prev_page_url,
            preview_next_url=next_page_url,
        ),
    )


@router.post("/fila/{row_id}/eliminar")
def admin_enrolled_subjects_delete_row(
    row_id: int,
    user: dict = Depends(load_user_dep),
    grupo: str = Form(""),
    alumno: str = Form(""),
):
    _require_perm(user)
    deleted = delete_enrolled_subject_row(row_id=row_id)
    if not deleted:
        return _alumno_redirect(
            grupo=grupo or None,
            alumno=alumno or None,
            status="error",
            msg="No se encontró la fila a eliminar.",
        )
    return _alumno_redirect(
        grupo=grupo or None,
        alumno=alumno or deleted.get("alumno") or None,
        status="deleted",
        msg=deleted.get("materia_abrev") or deleted.get("materia") or "",
    )


@router.post("/alumno/anadir")
def admin_enrolled_subjects_add_row(
    user: dict = Depends(load_user_dep),
    grupo: str = Form(""),
    alumno: str = Form(...),
    materia_abrev: str = Form(""),
    materia: str = Form(""),
    bilingue: str = Form(""),
    estudio: str = Form(""),
):
    _require_perm(user)
    alumno_v = (alumno or "").strip()
    if not alumno_v:
        return _alumno_redirect(
            grupo=grupo or None,
            status="error",
            msg="Seleccione un alumno antes de añadir una asignatura.",
        )
    try:
        created = add_enrolled_subject_for_alumno(
            alumno=alumno_v,
            materia_abrev=materia_abrev,
            materia=materia,
            bilingue=bilingue,
            estudio=estudio,
        )
    except ValueError as exc:
        return _alumno_redirect(
            grupo=grupo or None,
            alumno=alumno_v,
            status="error",
            msg=str(exc),
        )
    except Exception:
        _log.exception("Error al añadir asignatura matriculada")
        return _alumno_redirect(
            grupo=grupo or None,
            alumno=alumno_v,
            status="error",
            msg="No se pudo añadir la asignatura.",
        )
    return _alumno_redirect(
        grupo=grupo or created.get("nombre_grupo") or None,
        alumno=alumno_v,
        status="added",
        msg=created.get("materia_abrev") or created.get("materia") or "",
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
