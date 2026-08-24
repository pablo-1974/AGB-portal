"""Rutas HTTP bajo ``/publicar-avisos``."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from auth import load_user_dep
from config import settings
from context import ctx, institution_display_name
from consultas.listados.pdf_list import generate_simple_table_pdf_bytes
from db.groups import group_exists, list_groups
from db.portal_published_notices import (
    ROLE_LABEL_AVISO_LIBRE,
    create_aviso_libre_notice,
    create_baja_alumno_notice,
    create_nuevo_alumno_notice,
    list_aviso_libre_notices,
    list_baja_alumno_notices,
    list_nuevo_alumno_notices,
    list_reincorporacion_notices,
    list_sustitucion_notices,
)
from db.students import get_students_by_group, student_exists
from publicar_avisos.avisos_tipo_data import AVISOS_TIPO
from utils.enums import PERM_PUBLICAR_AVISOS_APP
from utils.permissions import has_permission

router = APIRouter(prefix="/publicar-avisos", tags=["publicar-avisos"])

_AVISOS_TIPO_BY_ID = {a["id"]: a for a in AVISOS_TIPO}


def _require_access(user: dict) -> None:
    if not has_permission(user, PERM_PUBLICAR_AVISOS_APP):
        raise HTTPException(status_code=403, detail="Sin permiso para Publicar avisos")


def _page(
    request: Request,
    *,
    user: dict,
    template: str,
    title: str,
    nav_section: str,
    **extra,
):
    _require_access(user)
    return request.app.state.templates.TemplateResponse(
        template,
        ctx(
            request,
            user=user,
            title=title,
            nav_section=nav_section,
            **extra,
        ),
    )


def _parse_date(raw: str) -> date | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


@router.get("/", include_in_schema=False)
def publicar_avisos_root(user: dict = Depends(load_user_dep)):
    _require_access(user)
    return RedirectResponse("/publicar-avisos/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
def publicar_avisos_dashboard(request: Request, user: dict = Depends(load_user_dep)):
    return _page(
        request,
        user=user,
        template="publicar_avisos/dashboard.html",
        title="Publicar avisos",
        nav_section="inicio",
    )


@router.get("/aviso-tipo", response_class=HTMLResponse)
def publicar_avisos_aviso_tipo(request: Request, user: dict = Depends(load_user_dep)):
    publicado = (request.query_params.get("publicado") or "").strip() == "1"
    return _page(
        request,
        user=user,
        template="publicar_avisos/aviso_tipo.html",
        title="Aviso tipo · Publicar avisos",
        nav_section="aviso-tipo",
        avisos_tipo=AVISOS_TIPO,
        publicado_ok=publicado,
    )


@router.get("/aviso-tipo/{tipo_id}", response_class=HTMLResponse)
def publicar_avisos_aviso_tipo_form(
    request: Request,
    tipo_id: str,
    user: dict = Depends(load_user_dep),
):
    aviso_tipo = _AVISOS_TIPO_BY_ID.get((tipo_id or "").strip())
    if not aviso_tipo:
        raise HTTPException(status_code=404, detail="Tipo de aviso no encontrado")
    return _page(
        request,
        user=user,
        template="publicar_avisos/aviso_tipo_form.html",
        title=f"{aviso_tipo['title']} · Publicar avisos",
        nav_section="aviso-tipo",
        aviso_tipo=aviso_tipo,
        groups=list_groups(),
        alumnos=[],
        today_iso=date.today().isoformat(),
        form={},
        error=None,
    )


@router.get("/api/alumnos")
def publicar_avisos_api_alumnos(
    grupo: str = "",
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    g = (grupo or "").strip()
    if not g:
        return []
    return get_students_by_group(g)


@router.post("/aviso-tipo/nuevo-alumno", response_class=HTMLResponse)
def publicar_avisos_nuevo_alumno_submit(
    request: Request,
    user: dict = Depends(load_user_dep),
    alumno_nombre: str = Form(...),
    fecha_incorporacion: str = Form(...),
    grupo: str = Form(...),
    optativas: str = Form(""),
    observaciones: str = Form(""),
):
    _require_access(user)
    aviso_tipo = _AVISOS_TIPO_BY_ID["nuevo-alumno"]
    form = {
        "alumno_nombre": (alumno_nombre or "").strip(),
        "fecha_incorporacion": (fecha_incorporacion or "").strip(),
        "grupo": (grupo or "").strip(),
        "optativas": (optativas or "").strip(),
        "observaciones": (observaciones or "").strip(),
    }
    fecha = _parse_date(form["fecha_incorporacion"])
    error: str | None = None
    if not form["alumno_nombre"]:
        error = "Indica el nombre del alumno."
    elif fecha is None:
        error = "Indica una fecha de incorporación válida."
    elif not form["grupo"]:
        error = "Selecciona un grupo."
    elif not group_exists(form["grupo"]):
        error = "El grupo seleccionado no es válido."

    if error:
        return _page(
            request,
            user=user,
            template="publicar_avisos/aviso_tipo_form.html",
            title=f"{aviso_tipo['title']} · Publicar avisos",
            nav_section="aviso-tipo",
            aviso_tipo=aviso_tipo,
            groups=list_groups(),
            alumnos=[],
            today_iso=date.today().isoformat(),
            form=form,
            error=error,
        )

    create_nuevo_alumno_notice(
        created_by=int(user["id"]),
        alumno_nombre=form["alumno_nombre"],
        fecha_incorporacion=fecha,
        grupo=form["grupo"],
        optativas=form["optativas"],
        observaciones=form["observaciones"],
    )
    return RedirectResponse("/publicar-avisos/aviso-tipo?publicado=1", status_code=303)


@router.post("/aviso-tipo/baja-alumno", response_class=HTMLResponse)
def publicar_avisos_baja_alumno_submit(
    request: Request,
    user: dict = Depends(load_user_dep),
    grupo: str = Form(...),
    alumno: str = Form(...),
    fecha_baja: str = Form(...),
):
    _require_access(user)
    aviso_tipo = _AVISOS_TIPO_BY_ID["baja-alumno"]
    form = {
        "grupo": (grupo or "").strip(),
        "alumno": (alumno or "").strip(),
        "fecha_baja": (fecha_baja or "").strip(),
    }
    fecha = _parse_date(form["fecha_baja"])
    alumnos = get_students_by_group(form["grupo"]) if form["grupo"] else []
    error: str | None = None
    if not form["grupo"]:
        error = "Selecciona un grupo."
    elif not group_exists(form["grupo"]):
        error = "El grupo seleccionado no es válido."
    elif not form["alumno"]:
        error = "Selecciona un alumno."
    elif not student_exists(grupo=form["grupo"], alumno=form["alumno"]):
        error = "El alumno no pertenece a ese grupo."
    elif fecha is None:
        error = "Indica una fecha válida."

    if error:
        return _page(
            request,
            user=user,
            template="publicar_avisos/aviso_tipo_form.html",
            title=f"{aviso_tipo['title']} · Publicar avisos",
            nav_section="aviso-tipo",
            aviso_tipo=aviso_tipo,
            groups=list_groups(),
            alumnos=alumnos,
            today_iso=date.today().isoformat(),
            form=form,
            error=error,
        )

    create_baja_alumno_notice(
        created_by=int(user["id"]),
        alumno_nombre=form["alumno"],
        fecha_baja=fecha,
        grupo=form["grupo"],
    )
    return RedirectResponse("/publicar-avisos/aviso-tipo?publicado=1", status_code=303)


@router.get("/aviso-libre", response_class=HTMLResponse)
def publicar_avisos_aviso_libre(request: Request, user: dict = Depends(load_user_dep)):
    rol_label = ROLE_LABEL_AVISO_LIBRE.get((user.get("role") or "").strip().lower(), "—")
    publicado = (request.query_params.get("publicado") or "").strip() == "1"
    return _page(
        request,
        user=user,
        template="publicar_avisos/aviso_libre.html",
        title="Aviso libre · Publicar avisos",
        nav_section="aviso-libre",
        rol_label=rol_label,
        form={},
        error=None,
        publicado_ok=publicado,
    )


@router.post("/aviso-libre", response_class=HTMLResponse)
def publicar_avisos_aviso_libre_submit(
    request: Request,
    user: dict = Depends(load_user_dep),
    mensaje: str = Form(""),
):
    _require_access(user)
    form = {"mensaje": (mensaje or "").strip()}
    rol_key = (user.get("role") or "").strip().lower()
    rol_label = ROLE_LABEL_AVISO_LIBRE.get(rol_key, "—")
    error: str | None = None
    if not form["mensaje"]:
        error = "Escribe el texto del aviso."
    elif rol_key not in ROLE_LABEL_AVISO_LIBRE:
        error = "Tu rol no puede publicar avisos libres."

    if error:
        return _page(
            request,
            user=user,
            template="publicar_avisos/aviso_libre.html",
            title="Aviso libre · Publicar avisos",
            nav_section="aviso-libre",
            rol_label=rol_label,
            form=form,
            error=error,
            publicado_ok=False,
        )

    create_aviso_libre_notice(
        created_by=user.get("id"),
        role=rol_key,
        mensaje=form["mensaje"],
    )
    return RedirectResponse("/publicar-avisos/aviso-libre?publicado=1", status_code=303)


@router.get("/listar", response_class=HTMLResponse)
def publicar_avisos_listar(request: Request, user: dict = Depends(load_user_dep)):
    return _page(
        request,
        user=user,
        template="publicar_avisos/listar.html",
        title="Listar avisos · Publicar avisos",
        nav_section="listar",
        alumnos_nuevos=list_nuevo_alumno_notices(),
        alumnos_baja=list_baja_alumno_notices(),
        sustituciones=list_sustitucion_notices(),
        reincorporaciones=list_reincorporacion_notices(),
        avisos_libres=list_aviso_libre_notices(),
    )


@router.get("/listar/alumnos-nuevos/export.pdf")
def publicar_avisos_alumnos_nuevos_pdf(user: dict = Depends(load_user_dep)):
    _require_access(user)
    rows_data = list_nuevo_alumno_notices()
    headers = ["Fecha", "Nombre", "Grupo", "Optativas"]
    rows = [
        [
            r["fecha_display"],
            r["alumno_nombre"],
            r["grupo"],
            r["optativas"] or "—",
        ]
        for r in rows_data
    ]
    if not rows:
        rows = [["—", "Sin registros", "—", "—"]]
    try:
        pdf_data = generate_simple_table_pdf_bytes(
            center_name=institution_display_name(settings.INSTITUTION_NAME),
            headline="Alumnos nuevos",
            headers=headers,
            rows=rows,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo generar el PDF: {exc}",
        ) from exc
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="alumnos-nuevos.pdf"'
        },
    )


@router.get("/listar/alumnos-baja/export.pdf")
def publicar_avisos_alumnos_baja_pdf(user: dict = Depends(load_user_dep)):
    _require_access(user)
    rows_data = list_baja_alumno_notices()
    headers = ["Fecha", "Alumno", "Grupo"]
    rows = [
        [r["fecha_display"], r["alumno_nombre"], r["grupo"]]
        for r in rows_data
    ]
    if not rows:
        rows = [["—", "Sin registros", "—"]]
    try:
        pdf_data = generate_simple_table_pdf_bytes(
            center_name=institution_display_name(settings.INSTITUTION_NAME),
            headline="Alumnos de baja",
            headers=headers,
            rows=rows,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo generar el PDF: {exc}",
        ) from exc
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="alumnos-baja.pdf"'
        },
    )


@router.get("/listar/sustituciones/export.pdf")
def publicar_avisos_sustituciones_pdf(user: dict = Depends(load_user_dep)):
    _require_access(user)
    rows_data = list_sustitucion_notices()
    headers = ["Fecha", "Sustituido", "Sustituto"]
    rows = [
        [r["fecha_display"], r["sustituido_alias"], r["sustituto_nombre"]]
        for r in rows_data
    ]
    if not rows:
        rows = [["—", "Sin registros", "—"]]
    try:
        pdf_data = generate_simple_table_pdf_bytes(
            center_name=institution_display_name(settings.INSTITUTION_NAME),
            headline="Sustituciones",
            headers=headers,
            rows=rows,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo generar el PDF: {exc}",
        ) from exc
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="sustituciones.pdf"'
        },
    )


@router.get("/listar/reincorporaciones/export.pdf")
def publicar_avisos_reincorporaciones_pdf(user: dict = Depends(load_user_dep)):
    _require_access(user)
    rows_data = list_reincorporacion_notices()
    headers = ["Fecha", "Sustituto", "Sustituido"]
    rows = [
        [
            r["fecha_display"],
            r["sustituto_nombre"] or "—",
            r["sustituido_alias"],
        ]
        for r in rows_data
    ]
    if not rows:
        rows = [["—", "Sin registros", "—"]]
    try:
        pdf_data = generate_simple_table_pdf_bytes(
            center_name=institution_display_name(settings.INSTITUTION_NAME),
            headline="Reincorporaciones",
            headers=headers,
            rows=rows,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo generar el PDF: {exc}",
        ) from exc
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="reincorporaciones.pdf"'
        },
    )


@router.get("/listar/avisos-libres/export.pdf")
def publicar_avisos_libres_pdf(user: dict = Depends(load_user_dep)):
    _require_access(user)
    rows_data = list_aviso_libre_notices()
    headers = ["Fecha", "Autor", "Texto"]
    rows = [
        [r["fecha_display"], r["autor"], r["texto"] or "—"]
        for r in rows_data
    ]
    if not rows:
        rows = [["—", "Sin registros", "—"]]
    try:
        pdf_data = generate_simple_table_pdf_bytes(
            center_name=institution_display_name(settings.INSTITUTION_NAME),
            headline="Avisos libres",
            headers=headers,
            rows=rows,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"No se pudo generar el PDF: {exc}",
        ) from exc
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="avisos-libres.pdf"'
        },
    )
