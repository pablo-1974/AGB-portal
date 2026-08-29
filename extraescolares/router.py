"""Rutas HTTP de Actividades extraescolares bajo ``/extraescolares``."""

from __future__ import annotations

import tempfile
from datetime import date, timedelta

from utils.time_madrid import today_madrid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.responses import Response

from config import settings
from context import ctx, institution_display_name
from db.groups import list_groups
from db.users import get_all_teachers
from extraescolares.calendar_view import (
    academic_year_month_bounds,
    build_extraescolares_calendar_months,
    calendario_filter_url,
    format_date_es,
    format_range_es,
    last_day_of_month,
    list_academic_month_options,
    month_param,
    resolve_desde_hasta,
    school_calendar_for_display,
    visible_date_range_for_months,
)
from extraescolares.deps import (
    require_extraescolares_access,
    require_extraescolares_delete,
    require_extraescolares_edit_confirmed,
    require_extraescolares_listado,
)
from utils.pdf_http import pdf_attachment_response, safe_pdf_filename
from utils.permissions import has_permission
from utils.enums import PERM_EXTRAESCOLARES_LISTADO
from utils.school_hours import hours_mask_from_form
from extraescolares.services.pdf_autorizacion import autorizacion_pdf_bytes
from extraescolares.services.pdf_actividad_resumen import build_actividad_resumen_pdf
from extraescolares.services.export_actividad_resumen import actividad_resumen_xlsx_bytes
from extraescolares.services.export_actividades_listado import (
    actividades_listado_docx_bytes,
    actividades_listado_pdf_bytes,
    actividades_listado_xlsx_bytes,
)
from db.action_logs import log_extraescolares_action
from db.extraescolares_access import (
    accept_extraescolares_normas,
    has_accepted_extraescolares_normas,
)
from extraescolares.normas_data import NORMAS_EXTRAESCOLARES_SECTIONS
from extraescolares.queries import (
    activities_by_date,
    cancel_extraescolar_by_organizer,
    confirm_extraescolar_by_organizer,
    delete_extraescolar_by_admin,
    attach_calendar_student_details,
    create_extraescolar_activity,
    get_extraescolar_for_responsable,
    get_extraescolar_by_id,
    list_departamentos_didacticos,
    list_extraescolares_between,
    list_extraescolares_by_responsable,
    list_students_for_groups,
    update_extraescolar_activity,
)

router = APIRouter(
    prefix="/extraescolares",
    tags=["extraescolares"],
    dependencies=[Depends(require_extraescolares_access)],
)

ExtraescolaresUser = Annotated[dict, Depends(require_extraescolares_access)]
ExtraescolaresListadoUser = Annotated[dict, Depends(require_extraescolares_listado)]
ExtraescolaresEditStaffUser = Annotated[dict, Depends(require_extraescolares_edit_confirmed)]
ExtraescolaresDeleteUser = Annotated[dict, Depends(require_extraescolares_delete)]


def _templates(request: Request):
    return request.app.state.templates


def _activity_log_detail(act: dict | None, act_id: int) -> str:
    if not act:
        return f"Actividad #{act_id}"
    title = (act.get("actividad") or "").strip() or f"#{act_id}"
    fd = act.get("fecha_iso") or act.get("fecha")
    if fd:
        return f"{title} · {fd}"
    return title


@router.get("/", include_in_schema=False)
def extraescolares_root():
    return RedirectResponse("/extraescolares/dashboard", status_code=303)


@router.get("/normas", response_class=HTMLResponse)
def extraescolares_normas(request: Request, user: ExtraescolaresUser):
    accepted = has_accepted_extraescolares_normas(user_id=int(user["id"]))
    return _templates(request).TemplateResponse(
        "extraescolares/normas.html",
        ctx(
            request,
            user=user,
            title="Normas · Extraescolares",
            nav_section="normas",
            normas_sections=NORMAS_EXTRAESCOLARES_SECTIONS,
            normas_accepted=accepted,
            normas_pending=not accepted,
        ),
    )


@router.post("/normas/aceptar")
def extraescolares_normas_aceptar(user: ExtraescolaresUser):
    accept_extraescolares_normas(user_id=int(user["id"]))
    return RedirectResponse("/extraescolares/dashboard", status_code=303)


def _school_date_bounds(school_cal: dict | None, *, today: date) -> tuple[date, date]:
    if school_cal and school_cal.get("first_date") and school_cal.get("last_day"):
        return school_cal["first_date"], school_cal["last_day"]
    start_month, end_month = academic_year_month_bounds(school_cal, today=today)
    return start_month, last_day_of_month(end_month)


def _min_fecha_nueva_actividad(school_min: date, *, today: date | None = None) -> date:
    """Primera fecha válida al crear: estrictamente futura (desde mañana)."""
    today = today or today_madrid()
    return max(school_min, today + timedelta(days=1))


def _actividad_edit_template_context(
    request: Request,
    user: dict,
    act: dict,
    *,
    staff_edit: bool,
    nav_section: str,
    form_error: str | None = None,
    saved_ok: bool = False,
) -> dict:
    today = today_madrid()
    school_cal = school_calendar_for_display()
    min_d, max_d = _school_date_bounds(school_cal, today=today)

    enrolled = [
        {
            "id": int(s["student_id"]),
            "grupo": s["grupo"],
            "alumno": s["alumno"],
            "estado": s["estado"],
            "estado_label": (
                "Confirmado"
                if (s.get("estado") or "").strip().lower() == "confirmado"
                else "No confirmado"
            ),
        }
        for s in act.get("students") or []
        if s.get("student_id") is not None
    ]
    enrolled_ids = [int(s["id"]) for s in enrolled]
    can_edit = act.get("is_editable") or staff_edit

    return ctx(
        request,
        user=user,
        title=f"{act['actividad']} · {'Actividades' if staff_edit else 'Mis actividades'}",
        nav_section=nav_section,
        staff_edit=staff_edit,
        act={
            **act,
            "fecha_display": format_date_es(act["fecha"]) if act.get("fecha") else "",
            "confirmation_deadline_display": (
                format_date_es(act["confirmation_deadline"])
                if act.get("confirmation_deadline")
                else ""
            ),
            "show_edit_form": can_edit,
        },
        enrolled_students=enrolled,
        enrolled_student_ids=[str(i) for i in enrolled_ids],
        fecha_min=max(min_d, today).isoformat() if can_edit else min_d.isoformat(),
        fecha_max=max_d.isoformat(),
        responsable_id=int(act["responsable_id"]),
        profesores=get_all_teachers(),
        grupos=list_groups(),
        acompanante_ids=act.get("acompanante_ids") or [],
        form_error=form_error,
        saved_ok=saved_ok,
    )


def _extraescolar_for_pdf(user: dict, act_id: int) -> dict | None:
    """Organizador o personal con listado puede descargar exportaciones de la actividad."""
    act = get_extraescolar_for_responsable(act_id, int(user["id"]))
    if act:
        return act
    if has_permission(user, PERM_EXTRAESCOLARES_LISTADO):
        return get_extraescolar_by_id(act_id)
    return None


def _actividad_export_stem(act: dict, act_id: int) -> str:
    return safe_pdf_filename(
        f"actividad_{act.get('actividad') or 'extraescolar'}_{act.get('fecha_iso') or act_id}",
        ext="pdf",
    ).removesuffix(".pdf")


def _autorizacion_form_defaults() -> dict:
    return {
        "centro_nombre": institution_display_name(settings.INSTITUTION_NAME),
        "coste_tipo": "gratuita",
    }


def _parse_autorizacion_form(
    *,
    centro_nombre: str,
    actividad_nombre: str,
    actividad_fecha: str,
    actividad_lugar: str,
    hora_desde: str,
    hora_hasta: str,
    caracteristicas: str,
    coste_tipo: str,
    coste_importe: str,
    entregar_a: str,
) -> tuple[dict | None, dict, str | None]:
    """Devuelve (datos_pdf, form_repoblar, error)."""
    form = {
        "centro_nombre": (centro_nombre or "").strip()
        or institution_display_name(settings.INSTITUTION_NAME),
        "actividad_nombre": (actividad_nombre or "").strip(),
        "actividad_fecha": (actividad_fecha or "").strip(),
        "actividad_lugar": (actividad_lugar or "").strip(),
        "hora_desde": (hora_desde or "").strip(),
        "hora_hasta": (hora_hasta or "").strip(),
        "caracteristicas": (caracteristicas or "").strip(),
        "coste_tipo": (coste_tipo or "gratuita").strip(),
        "coste_importe": (coste_importe or "").strip(),
        "entregar_a": (entregar_a or "").strip(),
    }

    required = [
        ("actividad_nombre", "Nombre de la actividad"),
        ("actividad_fecha", "Fecha de la actividad"),
        ("actividad_lugar", "Lugar"),
        ("hora_desde", "Horario desde"),
        ("hora_hasta", "Horario hasta"),
        ("caracteristicas", "Características de la actividad"),
        ("entregar_a", "Entregar en el centro a"),
    ]
    for key, label in required:
        if not form[key]:
            return None, form, f"Complete el campo «{label}»."

    try:
        fecha_obj = date.fromisoformat(form["actividad_fecha"])
    except ValueError:
        return None, form, "La fecha de la actividad no es válida."

    gratuita = form["coste_tipo"] == "gratuita"
    if not gratuita and not form["coste_importe"]:
        return None, form, "Indique el importe o marque la actividad como gratuita."

    pdf_data = {
        **form,
        "coste_gratuita": gratuita,
        "actividad_fecha_display": format_date_es(fecha_obj),
    }
    return pdf_data, form, None


@router.get("/autorizaciones", response_class=HTMLResponse)
def extraescolares_autorizaciones_form(request: Request, user: ExtraescolaresUser):
    return _templates(request).TemplateResponse(
        "extraescolares/autorizaciones.html",
        ctx(
            request,
            user=user,
            title="Autorizaciones · Actividades extraescolares",
            nav_section="autorizaciones",
            form=_autorizacion_form_defaults(),
            form_error=None,
        ),
    )


@router.post("/autorizaciones/pdf")
def extraescolares_autorizaciones_pdf(
    request: Request,
    user: ExtraescolaresUser,
    centro_nombre: str = Form(""),
    actividad_nombre: str = Form(""),
    actividad_fecha: str = Form(""),
    actividad_lugar: str = Form(""),
    hora_desde: str = Form(""),
    hora_hasta: str = Form(""),
    caracteristicas: str = Form(""),
    coste_tipo: str = Form("gratuita"),
    coste_importe: str = Form(""),
    entregar_a: str = Form(""),
):
    pdf_data, form, err = _parse_autorizacion_form(
        centro_nombre=centro_nombre,
        actividad_nombre=actividad_nombre,
        actividad_fecha=actividad_fecha,
        actividad_lugar=actividad_lugar,
        hora_desde=hora_desde,
        hora_hasta=hora_hasta,
        caracteristicas=caracteristicas,
        coste_tipo=coste_tipo,
        coste_importe=coste_importe,
        entregar_a=entregar_a,
    )
    if err or pdf_data is None:
        return _templates(request).TemplateResponse(
            "extraescolares/autorizaciones.html",
            ctx(
                request,
                user=user,
                title="Autorizaciones · Actividades extraescolares",
                nav_section="autorizaciones",
                form=form,
                form_error=err,
            ),
            status_code=400,
        )

    try:
        pdf_bytes = autorizacion_pdf_bytes(pdf_data)
    except Exception as exc:
        return _templates(request).TemplateResponse(
            "extraescolares/autorizaciones.html",
            ctx(
                request,
                user=user,
                title="Autorizaciones · Actividades extraescolares",
                nav_section="autorizaciones",
                form=form,
                form_error=f"No se pudo generar el PDF: {exc}",
            ),
            status_code=500,
        )
    stem = safe_pdf_filename(
        f"autorizacion_{pdf_data['actividad_nombre']}_{actividad_fecha}",
        ext="pdf",
    ).removesuffix(".pdf")
    fn = safe_pdf_filename(stem, ext="pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/dashboard", response_class=HTMLResponse)
def extraescolares_dashboard(request: Request, user: ExtraescolaresUser):
    return _templates(request).TemplateResponse(
        "extraescolares/dashboard.html",
        ctx(
            request,
            user=user,
            title="Actividades extraescolares",
            portal_shell_title="Actividades extraescolares",
        ),
    )


@router.get("/nueva", response_class=HTMLResponse)
def extraescolares_nueva_form(
    request: Request,
    user: ExtraescolaresUser,
    fecha: str | None = Query(None),
):
    today = today_madrid()
    school_cal = school_calendar_for_display()
    min_d, max_d = _school_date_bounds(school_cal, today=today)
    fecha_min = _min_fecha_nueva_actividad(min_d, today=today)
    prefill = (fecha or "").strip()[:10]
    if prefill:
        try:
            fd = date.fromisoformat(prefill)
            if fd < fecha_min or fd > max_d:
                prefill = fecha_min.isoformat()
        except ValueError:
            prefill = fecha_min.isoformat()
    else:
        prefill = fecha_min.isoformat()

    return _templates(request).TemplateResponse(
        "extraescolares/nueva.html",
        ctx(
            request,
            user=user,
            title="Nueva actividad · Actividades extraescolares",
            nav_section="nueva",
            departamentos=list_departamentos_didacticos(),
            grupos=list_groups(),
            fecha_min=fecha_min.isoformat(),
            fecha_max=max_d.isoformat(),
            fecha_prefill=prefill,
            lugar_placeholder=settings.INSTITUTION_NAME,
            responsable_name=(user.get("name") or "").strip(),
            responsable_id=int(user["id"]),
            profesores=get_all_teachers(),
        ),
    )


@router.get("/nueva/alumnos")
def extraescolares_nueva_alumnos_json(
    user: ExtraescolaresUser,
    grupos: list[str] = Query(default=[]),
):
    rows = list_students_for_groups(grupos)
    return JSONResponse(rows)


@router.post("/nueva")
def extraescolares_nueva_post(
    user: ExtraescolaresUser,
    fecha: str = Form(...),
    actividad: str = Form(...),
    lugar: str = Form(""),
    departamento: str = Form(...),
    hours_mode: str = Form("all"),
    hour_from: int | None = Form(default=None),
    hour_to: int | None = Form(default=None),
    acompanante_ids: list[int] = Form(default=[]),
    grupos: list[str] = Form(default=[]),
    student_ids: list[int] = Form(default=[]),
):
    dest = "/extraescolares/nueva"
    try:
        fd = date.fromisoformat((fecha or "").strip()[:10])
    except ValueError:
        return RedirectResponse(f"{dest}?status=error&msg={quote('Fecha no válida')}", status_code=303)

    school_cal = school_calendar_for_display()
    today = today_madrid()
    min_d, max_d = _school_date_bounds(school_cal, today=today)
    fecha_min = _min_fecha_nueva_actividad(min_d, today=today)
    if fd < fecha_min or fd > max_d:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote('La fecha debe estar dentro del curso escolar')}",
            status_code=303,
        )
    if fd <= today:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote('Solo se pueden crear actividades en fechas futuras')}",
            status_code=303,
        )

    hours_mask = hours_mask_from_form(hours_mode, hour_from, hour_to)
    if hours_mask is None:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote('Seleccione un rango válido de horas de ausencia')}",
            status_code=303,
        )

    try:
        act_id = create_extraescolar_activity(
            fecha=fd,
            actividad=actividad,
            lugar=lugar,
            departamento=departamento,
            responsable_id=int(user["id"]),
            hours_mask=hours_mask,
            acompanante_ids=acompanante_ids,
            student_ids=student_ids,
        )
    except ValueError as exc:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote(str(exc))}",
            status_code=303,
        )

    log_extraescolares_action(
        user_id=int(user["id"]),
        action="activity_create",
        entity_id=int(act_id),
        detail=f"Alta: {actividad.strip()} · {fd.isoformat()}",
    )

    mes = month_param(fd)
    return RedirectResponse(
        f"/extraescolares/calendario?desde={mes}&hasta={mes}&status=created&act_id={act_id}",
        status_code=303,
    )


def _format_activities_for_display(activities: list[dict]) -> list[dict]:
    out = []
    for act in activities:
        fd = act.get("fecha")
        out.append(
            {
                **act,
                "fecha_display": format_date_es(fd) if fd else act.get("fecha_iso", ""),
                "confirmation_deadline_display": (
                    format_date_es(act["confirmation_deadline"])
                    if act.get("confirmation_deadline")
                    else ""
                ),
            }
        )
    return out


@router.get("/mis-actividades", response_class=HTMLResponse)
def extraescolares_mis_actividades(request: Request, user: ExtraescolaresUser):
    today = today_madrid()
    school_cal = school_calendar_for_display()
    min_d, max_d = _school_date_bounds(school_cal, today=today)
    all_acts = _format_activities_for_display(
        list_extraescolares_by_responsable(int(user["id"]), min_d, max_d)
    )
    futuras = [a for a in all_acts if not a["is_past"]]
    pasadas = sorted(
        [a for a in all_acts if a["is_past"]],
        key=lambda a: a.get("fecha_iso") or "",
        reverse=True,
    )
    year_label = school_cal.get("school_year") if school_cal else format_range_es(min_d, max_d)

    return _templates(request).TemplateResponse(
        "extraescolares/mis_actividades.html",
        ctx(
            request,
            user=user,
            title="Mis actividades · Actividades extraescolares",
            nav_section="mis",
            futuras=futuras,
            pasadas=pasadas,
            year_label=year_label,
            saved_ok=request.query_params.get("status") == "saved",
            confirmed_ok=request.query_params.get("status") == "confirmed",
        ),
    )


def _sort_activities_by_date(
    activities: list[dict],
    *,
    reverse: bool = False,
) -> list[dict]:
    return sorted(
        activities,
        key=lambda a: (
            a.get("fecha_iso") or "",
            (a.get("actividad") or "").lower(),
        ),
        reverse=reverse,
    )


def _actividades_curso_data() -> tuple[list[dict], list[dict], str]:
    today = today_madrid()
    school_cal = school_calendar_for_display()
    min_d, max_d = _school_date_bounds(school_cal, today=today)
    raw = attach_calendar_student_details(
        list_extraescolares_between(min_d, max_d)
    )
    all_acts = _format_activities_for_display(raw)
    programadas = _sort_activities_by_date(
        [a for a in all_acts if not a["is_past"]],
        reverse=False,
    )
    realizadas = _sort_activities_by_date(
        [a for a in all_acts if a["is_past"]],
        reverse=True,
    )
    year_label = (
        school_cal.get("school_year") if school_cal else format_range_es(min_d, max_d)
    )
    return programadas, realizadas, year_label


@router.get("/actividades", response_class=HTMLResponse)
def extraescolares_actividades_listado(
    request: Request,
    user: ExtraescolaresListadoUser,
):
    programadas, realizadas, year_label = _actividades_curso_data()

    return _templates(request).TemplateResponse(
        "extraescolares/actividades.html",
        ctx(
            request,
            user=user,
            title="Actividades · Actividades extraescolares",
            nav_section="actividades",
            programadas=programadas,
            realizadas=realizadas,
            year_label=year_label,
        ),
    )


@router.get("/actividades/exportar.pdf")
def extraescolares_actividades_export_pdf(user: ExtraescolaresListadoUser):
    programadas, realizadas, year_label = _actividades_curso_data()
    data = actividades_listado_pdf_bytes(
        year_label=year_label,
        programadas=programadas,
        realizadas=realizadas,
    )
    fn = safe_pdf_filename(f"actividades_extraescolares_{year_label}", ext="pdf")
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/actividades/exportar.xlsx")
def extraescolares_actividades_export_xlsx(user: ExtraescolaresListadoUser):
    programadas, realizadas, year_label = _actividades_curso_data()
    data = actividades_listado_xlsx_bytes(
        year_label=year_label,
        programadas=programadas,
        realizadas=realizadas,
    )
    fn = safe_pdf_filename(f"actividades_extraescolares_{year_label}", ext="xlsx")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/actividades/exportar.docx")
def extraescolares_actividades_export_docx(user: ExtraescolaresListadoUser):
    programadas, realizadas, year_label = _actividades_curso_data()
    data = actividades_listado_docx_bytes(
        year_label=year_label,
        programadas=programadas,
        realizadas=realizadas,
    )
    fn = safe_pdf_filename(f"actividades_extraescolares_{year_label}", ext="docx")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.get("/actividades/{act_id}/editar", response_class=HTMLResponse)
def extraescolares_actividad_editar_staff(
    request: Request,
    user: ExtraescolaresEditStaffUser,
    act_id: int,
):
    act = get_extraescolar_by_id(act_id)
    if not act or not act.get("is_staff_editable"):
        raise HTTPException(status_code=404, detail="Actividad no encontrada o no editable")

    return _templates(request).TemplateResponse(
        "extraescolares/mis_actividades_detalle.html",
        _actividad_edit_template_context(
            request,
            user,
            act,
            staff_edit=True,
            nav_section="actividades",
            form_error=(request.query_params.get("msg") or "").strip() or None,
            saved_ok=request.query_params.get("status") == "saved",
        ),
    )


@router.post("/actividades/{act_id}/editar")
def extraescolares_actividad_editar_staff_post(
    user: ExtraescolaresEditStaffUser,
    act_id: int,
    fecha: str = Form(...),
    acompanante_ids: list[int] = Form(default=[]),
    student_ids: list[int] = Form(default=[]),
):
    dest = f"/extraescolares/actividades/{act_id}/editar"
    try:
        fd = date.fromisoformat((fecha or "").strip()[:10])
    except ValueError:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote('Fecha no válida')}",
            status_code=303,
        )

    school_cal = school_calendar_for_display()
    min_d, max_d = _school_date_bounds(school_cal, today=today_madrid())
    if fd < min_d or fd > max_d:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote('La fecha debe estar dentro del curso escolar')}",
            status_code=303,
        )
    if fd < today_madrid():
        return RedirectResponse(
            f"{dest}?status=error&msg={quote('La fecha debe ser hoy o un día futuro')}",
            status_code=303,
        )

    try:
        update_extraescolar_activity(
            activity_id=act_id,
            editor_id=int(user["id"]),
            fecha=fd,
            student_ids=student_ids,
            acompanante_ids=acompanante_ids,
            as_staff=True,
        )
    except ValueError as exc:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote(str(exc))}",
            status_code=303,
        )

    act = get_extraescolar_by_id(act_id)
    log_extraescolares_action(
        user_id=int(user["id"]),
        action="activity_update_staff",
        entity_id=act_id,
        detail=f"Edición jefatura: {_activity_log_detail(act, act_id)}",
    )

    return RedirectResponse(f"{dest}?status=saved", status_code=303)


@router.get("/mis-actividades/{act_id}", response_class=HTMLResponse)
def extraescolares_mis_actividad_detalle(
    request: Request,
    user: ExtraescolaresUser,
    act_id: int,
):
    act = get_extraescolar_for_responsable(act_id, int(user["id"]))
    if not act:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")

    if not act:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")

    return _templates(request).TemplateResponse(
        "extraescolares/mis_actividades_detalle.html",
        _actividad_edit_template_context(
            request,
            user,
            act,
            staff_edit=False,
            nav_section="mis",
            form_error=(request.query_params.get("msg") or "").strip() or None,
            saved_ok=request.query_params.get("status") == "saved",
        ),
    )


@router.post("/mis-actividades/{act_id}")
def extraescolares_mis_actividad_update(
    user: ExtraescolaresUser,
    act_id: int,
    fecha: str = Form(...),
    acompanante_ids: list[int] = Form(default=[]),
    student_ids: list[int] = Form(default=[]),
):
    dest = f"/extraescolares/mis-actividades/{act_id}"
    try:
        fd = date.fromisoformat((fecha or "").strip()[:10])
    except ValueError:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote('Fecha no válida')}",
            status_code=303,
        )

    school_cal = school_calendar_for_display()
    min_d, max_d = _school_date_bounds(school_cal, today=today_madrid())
    if fd < min_d or fd > max_d:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote('La fecha debe estar dentro del curso escolar')}",
            status_code=303,
        )
    if fd < today_madrid():
        return RedirectResponse(
            f"{dest}?status=error&msg={quote('La fecha debe ser hoy o un día futuro')}",
            status_code=303,
        )

    try:
        update_extraescolar_activity(
            activity_id=act_id,
            editor_id=int(user["id"]),
            fecha=fd,
            student_ids=student_ids,
            acompanante_ids=acompanante_ids,
            as_staff=False,
        )
    except ValueError as exc:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote(str(exc))}",
            status_code=303,
        )

    act = get_extraescolar_for_responsable(act_id, int(user["id"]))
    log_extraescolares_action(
        user_id=int(user["id"]),
        action="activity_update",
        entity_id=act_id,
        detail=f"Edición: {_activity_log_detail(act, act_id)}",
    )

    return RedirectResponse(f"{dest}?status=saved", status_code=303)


@router.get("/actividades/{act_id}/pdf")
def extraescolares_actividad_pdf(user: ExtraescolaresUser, act_id: int):
    act = _extraescolar_for_pdf(user, act_id)
    if not act:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()
    build_actividad_resumen_pdf(tmp.name, act)
    stem = _actividad_export_stem(act, act_id)
    return pdf_attachment_response(tmp.name, filename=f"{stem}.pdf")


@router.get("/actividades/{act_id}/xlsx")
def extraescolares_actividad_xlsx(user: ExtraescolaresUser, act_id: int):
    act = _extraescolar_for_pdf(user, act_id)
    if not act:
        raise HTTPException(status_code=404, detail="Actividad no encontrada")

    stem = _actividad_export_stem(act, act_id)
    data = actividad_resumen_xlsx_bytes(act)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{stem}.xlsx"'},
    )


@router.get("/mis-actividades/{act_id}/pdf")
def extraescolares_mis_actividad_pdf(user: ExtraescolaresUser, act_id: int):
    return extraescolares_actividad_pdf(user, act_id)


@router.get("/mis-actividades/{act_id}/xlsx")
def extraescolares_mis_actividad_xlsx(user: ExtraescolaresUser, act_id: int):
    return extraescolares_actividad_xlsx(user, act_id)


@router.post("/mis-actividades/{act_id}/confirmar")
def extraescolares_mis_actividad_confirmar(
    user: ExtraescolaresUser,
    act_id: int,
):
    dest = "/extraescolares/mis-actividades"
    try:
        confirm_extraescolar_by_organizer(
            activity_id=act_id,
            responsable_id=int(user["id"]),
        )
    except ValueError as exc:
        return RedirectResponse(
            f"/extraescolares/mis-actividades/{act_id}?status=error&msg={quote(str(exc))}",
            status_code=303,
        )
    act = get_extraescolar_for_responsable(act_id, int(user["id"]))
    log_extraescolares_action(
        user_id=int(user["id"]),
        action="activity_confirm",
        entity_id=act_id,
        detail=f"Confirmación: {_activity_log_detail(act, act_id)}",
    )
    return RedirectResponse(f"{dest}?status=confirmed", status_code=303)


@router.post("/mis-actividades/{act_id}/anular")
def extraescolares_mis_actividad_anular(
    user: ExtraescolaresUser,
    act_id: int,
):
    dest = f"/extraescolares/mis-actividades/{act_id}"
    try:
        cancel_extraescolar_by_organizer(
            activity_id=act_id,
            responsable_id=int(user["id"]),
        )
    except ValueError as exc:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote(str(exc))}",
            status_code=303,
        )
    act = get_extraescolar_for_responsable(act_id, int(user["id"]))
    log_extraescolares_action(
        user_id=int(user["id"]),
        action="activity_cancel",
        entity_id=act_id,
        detail=f"Anulación: {_activity_log_detail(act, act_id)}",
    )
    return RedirectResponse(f"{dest}?status=cancelled", status_code=303)


@router.post("/actividades/{act_id}/eliminar")
def extraescolares_actividad_eliminar(
    user: ExtraescolaresDeleteUser,
    act_id: int,
):
    dest = "/extraescolares/actividades"
    act = get_extraescolar_by_id(act_id)
    try:
        delete_extraescolar_by_admin(activity_id=act_id)
    except ValueError as exc:
        return RedirectResponse(
            f"{dest}?status=error&msg={quote(str(exc))}",
            status_code=303,
        )
    log_extraescolares_action(
        user_id=int(user["id"]),
        action="activity_delete",
        entity_id=act_id,
        detail=f"Eliminación (admin): {_activity_log_detail(act, act_id)}",
    )
    return RedirectResponse(f"{dest}?status=deleted", status_code=303)


def _activity_panel_fields(act: dict) -> dict:
    """Campos serializables para el panel Alpine del calendario."""
    return {
        "id": act["id"],
        "actividad": act["actividad"],
        "lugar": act["lugar"],
        "departamento": act["departamento"],
        "responsable_name": act["responsable_name"],
        "hours_display": act.get("hours_display"),
        "acompanantes_names": act.get("acompanantes_names"),
        "grupos": act.get("grupos") or [],
        "grupos_label": act.get("grupos_label"),
        "students": act.get("students") or [],
        "total_alumnos": act["total_alumnos"],
        "confirmados": act["confirmados"],
    }


@router.get("/calendario", response_class=HTMLResponse)
def extraescolares_calendario(
    request: Request,
    user: ExtraescolaresUser,
    desde: str | None = Query(None, description="Mes inicial YYYY-MM"),
    hasta: str | None = Query(None, description="Mes final YYYY-MM"),
    mes: str | None = Query(None, description="Compatibilidad: equivale a desde"),
):
    today = today_madrid()
    school_cal = school_calendar_for_display()
    start_month, end_month = academic_year_month_bounds(school_cal, today=today)
    month_options = list_academic_month_options(start_month, end_month)

    desde_month, hasta_month = resolve_desde_hasta(
        desde,
        hasta,
        mes,
        today=today,
        start_month=start_month,
        end_month=end_month,
    )
    range_start, range_end = visible_date_range_for_months(desde_month, hasta_month)
    raw = attach_calendar_student_details(
        list_extraescolares_between(range_start, range_end, include_cancelled=False)
    )
    by_date_raw = activities_by_date(raw)

    by_date: dict[str, list[dict]] = {}
    for iso, items in by_date_raw.items():
        by_date[iso] = [_activity_panel_fields(a) for a in items]

    months = build_extraescolares_calendar_months(
        desde_month,
        hasta_month,
        school_cal=school_cal,
        by_date=by_date,
    )

    activities_table = []
    for act in raw:
        fd = act.get("fecha")
        activities_table.append(
            {
                **act,
                "fecha_display": format_date_es(fd) if fd else act.get("fecha_iso", ""),
            }
        )

    return _templates(request).TemplateResponse(
        "extraescolares/calendario.html",
        ctx(
            request,
            user=user,
            title="Calendario · Actividades extraescolares",
            nav_section="calendario",
            months=months,
            activities=activities_table,
            range_label=format_range_es(range_start, range_end),
            today_display=format_date_es(today),
            school_year=school_cal.get("school_year") if school_cal else None,
            month_options=month_options,
            selected_desde=month_param(desde_month),
            selected_hasta=month_param(hasta_month),
            reset_url=calendario_filter_url(desde=start_month, hasta=end_month),
            created_ok=request.query_params.get("status") == "created",
        ),
    )
