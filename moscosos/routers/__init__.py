"""Rutas HTTP de la app moscosos bajo ``/moscosos``."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from config import settings
from context import ctx
from db.moscosos_calendar import (
    booking_calendar_visible_range,
    buffer_last_booking_date,
    build_booking_calendar_months,
    max_booking_date,
    moscosos_calendar_bundle,
)
from db.action_logs import log_moscosos_action
from db.moscosos_reservations import (
    MAX_RESERVATIONS_PER_USER_PER_COURSE,
    cancel_user_reservation,
    create_reservation,
    get_user_reservation,
    list_reservations_cuadro,
    list_user_reservations,
    mark_documentation_sent,
    reservation_counts_between,
    reservation_counts_by_user,
    reservations_by_date_for_cuadro,
)
from db.users import get_all_professors_cuadro
from db.school_calendar import MES_ES
from moscosos.booking import (
    TRIMESTER_NUM_LABEL,
    trimester_number_for_date,
    validate_new_reservation,
)
from moscosos.deps import require_moscosos_access, require_moscosos_staff
from moscosos.email_docs import (
    MAX_PDF_BYTES,
    EmailDeliveryError,
    EmailNotConfiguredError,
    is_smtp_configured,
    send_anexo_email,
    smtp_missing_keys,
)
from moscosos.cuadro_general import (
    attach_day_details_to_month,
    build_cuadro_month,
    build_month_days_detail,
    build_month_nav,
    build_month_options,
    build_resumen_curso,
    build_resumen_table_rows,
    default_month_first,
    parse_date_param,
    parse_month_param,
)
from moscosos.normas_data import NORMAS_RESERVA_MOSCOSOS

router = APIRouter(
    prefix="/moscosos",
    tags=["moscosos"],
    dependencies=[Depends(require_moscosos_access)],
)

MoscososUser = Annotated[dict, Depends(require_moscosos_access)]
MoscososStaffUser = Annotated[dict, Depends(require_moscosos_staff)]


def _templates(request: Request):
    return request.app.state.templates


def _format_date_es(d: date) -> str:
    return f"{d.day} de {MES_ES[d.month].lower()} de {d.year}"


def _doc_filename_example(user: dict, reservation_date: date) -> str:
    name = (user.get("name") or "").strip()
    institution = settings.INSTITUTION_NAME.strip().upper()
    date_part = reservation_date.strftime("%d-%m-%Y")
    return f"{name} – {institution} – {date_part}"


def _reservar_context(request: Request, user: dict, bundle: dict | None, today: date):
    if not bundle:
        return {
            "calendar_ready": False,
            "mis_reservas": [],
            "reservas_cupo_usado": 0,
            "reservas_cupo_max": MAX_RESERVATIONS_PER_USER_PER_COURSE,
            "puede_reservar": False,
        }
    cal_id = int(bundle["calendar"]["id"])
    mis = list_user_reservations(school_calendar_id=cal_id, user_id=int(user["id"]))
    mis_rows = []
    for r in mis:
        is_past = r.reservation_date < today
        doc_sent = r.has_documentation_sent
        mis_rows.append(
            {
                "id": r.id,
                "date_display": _format_date_es(r.reservation_date),
                "trimester_label": TRIMESTER_NUM_LABEL.get(
                    r.trimester, f"trimestre {r.trimester}"
                ),
                "can_cancel": not is_past and not doc_sent,
                "can_send_doc": not is_past,
                "doc_sent": doc_sent,
                "is_past": is_past,
            }
        )
    cupo_usado = len(mis)
    hay_reservas_anulables = any(row["can_cancel"] for row in mis_rows)
    hay_pendiente_documentacion = any(row["can_send_doc"] for row in mis_rows)
    first_bookable = buffer_last_booking_date(today) + timedelta(days=1)
    last_bookable = max_booking_date(today, bundle["course_end_date"])
    prefill_raw = (request.query_params.get("fecha") or "").strip()
    prefill_date = None
    prefill_display = None
    if prefill_raw:
        try:
            prefill_d = date.fromisoformat(prefill_raw)
            if first_bookable <= prefill_d <= last_bookable:
                prefill_date = prefill_raw
                prefill_display = _format_date_es(prefill_d)
        except ValueError:
            pass
    return {
        "calendar_ready": True,
        "mis_reservas": mis_rows,
        "reservas_cupo_usado": cupo_usado,
        "reservas_cupo_max": MAX_RESERVATIONS_PER_USER_PER_COURSE,
        "puede_reservar": cupo_usado < MAX_RESERVATIONS_PER_USER_PER_COURSE,
        "hay_reservas_anulables": hay_reservas_anulables,
        "hay_pendiente_documentacion": hay_pendiente_documentacion,
        "min_date": first_bookable.isoformat(),
        "max_date": last_bookable.isoformat(),
        "prefill_date": prefill_date,
        "prefill_display": prefill_display,
        "first_bookable_display": _format_date_es(first_bookable),
        "last_bookable_display": _format_date_es(last_bookable),
    }


def _reservar_url(status: str) -> str:
    return f"/moscosos/reservar?status={status}"


def _documentacion_url(reservation_id: int, status: str) -> str:
    return f"/moscosos/reservar/documentacion/{reservation_id}?status={status}"


def _load_own_reservation(user: dict, reservation_id: int, today: date):
    """Reserva del usuario; solo fechas futuras o de hoy pueden enviar documentación."""
    reservation = get_user_reservation(
        reservation_id=reservation_id, user_id=int(user["id"])
    )
    if not reservation:
        return None
    if reservation.reservation_date < today:
        return None
    return reservation


@router.get("/", include_in_schema=False)
def moscosos_root():
    return RedirectResponse("/moscosos/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
def moscosos_dashboard(request: Request, user: MoscososUser):
    return _templates(request).TemplateResponse(
        "moscosos/dashboard.html",
        ctx(request, user=user, title="Moscosos"),
    )


@router.get("/cuadro-general", response_class=HTMLResponse)
def moscosos_cuadro_general(request: Request, user: MoscososStaffUser):
    today = date.today()
    qp = request.query_params
    vista = (qp.get("vista") or "meses").strip().lower()
    if vista not in ("meses", "profesores", "resumen"):
        vista = "meses"

    bundle = moscosos_calendar_bundle()
    if not bundle:
        return _templates(request).TemplateResponse(
            "moscosos/cuadro_general.html",
            ctx(
                request,
                user=user,
                title="Cuadro General · Moscosos",
                calendar_ready=False,
                vista=vista,
            ),
        )

    cal = bundle["calendar"]
    cal_id = int(cal["id"])
    school_first = cal["first_date"]
    school_last = cal["last_day"]

    professors = get_all_professors_cuadro()
    prof_options = [{"id": "", "label": "Todos", "selected": True}]
    raw_prof = (qp.get("profesor_id") or "").strip()
    prof_id: int | None = None
    if raw_prof and raw_prof.isdigit():
        prof_id = int(raw_prof)
    for p in professors:
        prof_options.append(
            {
                "id": str(p["id"]),
                "label": p["label"],
                "selected": prof_id == p["id"],
            }
        )
    if prof_id is not None:
        prof_options[0]["selected"] = False

    date_from = parse_date_param(qp.get("desde"), default=school_first)
    date_to = parse_date_param(qp.get("hasta"), default=school_last)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    resumen_cols = build_resumen_curso(
        all_users=professors,
        counts_by_user=reservation_counts_by_user(school_calendar_id=cal_id),
    )
    resumen_rows = build_resumen_table_rows(resumen_cols)

    month_grid = None
    month_days_detail = {}
    month_options: list[dict] = []
    month_nav: dict[str, str | None] = {"prev": None, "next": None}
    prof_rows: list[dict] = []

    if vista == "meses":
        all_rows = list_reservations_cuadro(
            school_calendar_id=cal_id,
            date_from=school_first,
            date_to=school_last,
            user_id=None,
        )
        res_by_date = reservations_by_date_for_cuadro(all_rows)
        default_m = default_month_first(
            school_first=school_first, school_last=school_last, today=today
        )
        month_first = parse_month_param(qp.get("mes"), default=default_m)
        if month_first.replace(day=1) < school_first.replace(day=1):
            month_first = school_first.replace(day=1)
        if month_first.replace(day=1) > school_last.replace(day=1):
            month_first = school_last.replace(day=1)
        month_grid = build_cuadro_month(
            month_first=month_first,
            today=today,
            cal=cal,
            excluded=bundle["excluded"],
            buffer_days=bundle["buffer_days"],
            course_start=bundle["course_start_date"],
            course_end=bundle["course_end_date"],
            reservations_by_date=res_by_date,
        )
        month_days_detail = build_month_days_detail(
            month_grid,
            format_date_es=_format_date_es,
            trimester_label_for=lambda t: TRIMESTER_NUM_LABEL.get(
                t, f"trimestre {t}"
            ),
        )
        month_grid = attach_day_details_to_month(month_grid, month_days_detail)
        month_options = build_month_options(
            school_first=school_first,
            school_last=school_last,
            selected=month_first,
        )
        month_nav = build_month_nav(
            school_first=school_first,
            school_last=school_last,
            current=month_first,
        )
    elif vista == "profesores":
        filtered_rows = list_reservations_cuadro(
            school_calendar_id=cal_id,
            date_from=date_from,
            date_to=date_to,
            user_id=prof_id,
        )
        for r in filtered_rows:
            prof_rows.append(
                {
                    **r,
                    "date_display": _format_date_es(r["reservation_date"]),
                    "trimester_label": TRIMESTER_NUM_LABEL.get(
                        r["trimester"], f"trimestre {r['trimester']}"
                    ),
                }
            )

    return _templates(request).TemplateResponse(
        "moscosos/cuadro_general.html",
        ctx(
            request,
            user=user,
            title="Cuadro General · Moscosos",
            calendar_ready=True,
            vista=vista,
            school_year=cal.get("school_year") or "",
            month_grid=month_grid,
            month_days_detail=month_days_detail,
            month_options=month_options,
            month_nav=month_nav,
            prof_options=prof_options,
            prof_rows=prof_rows,
            resumen_cols=resumen_cols,
            resumen_rows=resumen_rows,
            filter_desde=date_from.isoformat(),
            filter_hasta=date_to.isoformat(),
            school_first_iso=school_first.isoformat(),
            school_last_iso=school_last.isoformat(),
        ),
    )


@router.get("/normas-reserva", response_class=HTMLResponse)
def moscosos_normas_reserva(request: Request, user: MoscososUser):
    return _templates(request).TemplateResponse(
        "moscosos/normas_reserva.html",
        ctx(
            request,
            user=user,
            title="Normas de reserva y tramitación · Moscosos",
            normas=NORMAS_RESERVA_MOSCOSOS,
        ),
    )


@router.get("/calendario", response_class=HTMLResponse)
def moscosos_calendario(request: Request, user: MoscososUser):
    today = date.today()
    bundle = moscosos_calendar_bundle()
    if not bundle:
        return _templates(request).TemplateResponse(
            "moscosos/calendario.html",
            ctx(
                request,
                user=user,
                title="Calendario · Moscosos",
                calendar_ready=False,
                today_display=_format_date_es(today),
            ),
        )

    range_start, range_end = booking_calendar_visible_range(today)
    cal_id = int(bundle["calendar"]["id"])
    reservation_counts = reservation_counts_between(
        school_calendar_id=cal_id,
        date_from=range_start,
        date_to=range_end,
    )
    months = build_booking_calendar_months(
        today,
        bundle["calendar"],
        bundle["excluded"],
        buffer_days=bundle["buffer_days"],
        course_start=bundle["course_start_date"],
        course_end=bundle["course_end_date"],
        reservation_counts=reservation_counts,
    )
    first_bookable = buffer_last_booking_date(today) + timedelta(days=1)
    last_bookable = max_booking_date(today, bundle["course_end_date"])
    last_limited_by_course_end = last_bookable < max_booking_date(today)
    return _templates(request).TemplateResponse(
        "moscosos/calendario.html",
        ctx(
            request,
            user=user,
            title="Calendario · Moscosos",
            calendar_ready=True,
            months=months,
            today_display=_format_date_es(today),
            first_bookable_display=_format_date_es(first_bookable),
            last_bookable_display=_format_date_es(last_bookable),
            last_limited_by_course_end=last_limited_by_course_end,
        ),
    )


@router.get("/reservar", response_class=HTMLResponse)
def moscosos_reservar_form(request: Request, user: MoscososUser):
    today = date.today()
    bundle = moscosos_calendar_bundle()
    return _templates(request).TemplateResponse(
        "moscosos/reservar.html",
        ctx(
            request,
            user=user,
            title="Reservar · Moscosos",
            **_reservar_context(request, user, bundle, today),
        ),
    )


@router.post("/reservar")
def moscosos_reservar_post(
    request: Request,
    user: MoscososUser,
    reservation_date: str = Form(...),
):
    today = date.today()
    bundle = moscosos_calendar_bundle()
    if not bundle:
        return RedirectResponse(_reservar_url("error"), status_code=303)

    try:
        d = date.fromisoformat(reservation_date.strip())
    except ValueError:
        return RedirectResponse(_reservar_url("error"), status_code=303)

    err = validate_new_reservation(
        user_id=int(user["id"]),
        reservation_date=d,
        today=today,
        bundle=bundle,
    )
    if err:
        return RedirectResponse(_reservar_url(err.code), status_code=303)

    trimester = trimester_number_for_date(
        d,
        bundle["calendar"],
        bundle["excluded"],
        course_start=bundle.get("course_start_date"),
        course_end=bundle.get("course_end_date"),
    )
    if trimester is None:
        return RedirectResponse(_reservar_url("not_bookable"), status_code=303)

    created = create_reservation(
        school_calendar_id=int(bundle["calendar"]["id"]),
        user_id=int(user["id"]),
        reservation_date=d,
        trimester=trimester,
    )
    if created is None:
        return RedirectResponse(_reservar_url("day_full"), status_code=303)

    log_moscosos_action(
        user_id=int(user["id"]),
        action="reservation_create",
        entity_id=int(created.id),
        detail=f"Reserva moscoso: {d.isoformat()} · trimestre {trimester} · plaza {created.slot}",
    )
    return RedirectResponse(_reservar_url("created"), status_code=303)


@router.post("/reservar/liberar")
def moscosos_reservar_liberar(
    user: MoscososUser,
    reservation_id: int = Form(...),
):
    today = date.today()
    reservation = get_user_reservation(
        reservation_id=reservation_id, user_id=int(user["id"])
    )
    if reservation and reservation.has_documentation_sent:
        return RedirectResponse(_reservar_url("doc_locked"), status_code=303)
    if cancel_user_reservation(
        reservation_id=reservation_id,
        user_id=int(user["id"]),
        today=today,
    ):
        detail = f"Anulación reserva #{reservation_id}"
        if reservation:
            detail = (
                f"Anulación moscoso: {reservation.reservation_date.isoformat()} "
                f"· reserva #{reservation_id}"
            )
        log_moscosos_action(
            user_id=int(user["id"]),
            action="reservation_cancel",
            entity_id=reservation_id,
            detail=detail,
        )
        return RedirectResponse(_reservar_url("released"), status_code=303)
    return RedirectResponse(_reservar_url("past_cancel"), status_code=303)


@router.get("/reservar/documentacion/{reservation_id}", response_class=HTMLResponse)
def moscosos_documentacion_form(
    reservation_id: int, request: Request, user: MoscososUser
):
    today = date.today()
    reservation = _load_own_reservation(user, reservation_id, today)
    if not reservation:
        raise HTTPException(status_code=404)
    return _templates(request).TemplateResponse(
        "moscosos/documentacion.html",
        ctx(
            request,
            user=user,
            title="Enviar documentación · Moscosos",
            reservation_id=reservation_id,
            date_display=_format_date_es(reservation.reservation_date),
            trimester_label=TRIMESTER_NUM_LABEL.get(
                reservation.trimester, f"trimestre {reservation.trimester}"
            ),
            doc_filename_example=_doc_filename_example(
                user, reservation.reservation_date
            ),
            doc_already_sent=reservation.has_documentation_sent,
            smtp_ready=is_smtp_configured(),
            smtp_missing=smtp_missing_keys(),
            dev_simulate=settings.MOSCOSOS_DOCS_DEV_SIMULATE,
        ),
    )


@router.post("/reservar/documentacion/{reservation_id}")
async def moscosos_documentacion_post(
    reservation_id: int,
    user: MoscososUser,
    pdf_file: UploadFile = File(...),
):
    today = date.today()
    reservation = _load_own_reservation(user, reservation_id, today)
    if not reservation:
        raise HTTPException(status_code=404)

    filename = (pdf_file.filename or "").strip() or "anexo.pdf"
    if not filename.lower().endswith(".pdf"):
        return RedirectResponse(
            _documentacion_url(reservation_id, "invalid"), status_code=303
        )

    content_type = (pdf_file.content_type or "").lower()
    if content_type and content_type not in ("application/pdf", "application/x-pdf"):
        return RedirectResponse(
            _documentacion_url(reservation_id, "invalid"), status_code=303
        )

    pdf_bytes = await pdf_file.read()
    if not pdf_bytes or len(pdf_bytes) > MAX_PDF_BYTES:
        return RedirectResponse(
            _documentacion_url(reservation_id, "invalid"), status_code=303
        )

    professor_name = (user.get("name") or "Profesor").strip()
    professor_email = (user.get("email") or "").strip()

    if not is_smtp_configured():
        if settings.MOSCOSOS_DOCS_DEV_SIMULATE:
            mark_documentation_sent(
                reservation_id=reservation_id, user_id=int(user["id"])
            )
            log_moscosos_action(
                user_id=int(user["id"]),
                action="documentation_sent",
                entity_id=reservation_id,
                detail=(
                    f"Documentación (modo prueba): "
                    f"{reservation.reservation_date.isoformat()}"
                ),
            )
            return RedirectResponse(_reservar_url("doc_sent"), status_code=303)
        return RedirectResponse(
            _documentacion_url(reservation_id, "smtp"), status_code=303
        )

    try:
        send_anexo_email(
            professor_name=professor_name,
            professor_email=professor_email,
            reservation_date=reservation.reservation_date,
            pdf_bytes=pdf_bytes,
            pdf_filename=filename,
        )
    except EmailNotConfiguredError:
        return RedirectResponse(
            _documentacion_url(reservation_id, "smtp"), status_code=303
        )
    except EmailDeliveryError:
        return RedirectResponse(
            _documentacion_url(reservation_id, "error"), status_code=303
        )

    mark_documentation_sent(
        reservation_id=reservation_id, user_id=int(user["id"])
    )
    log_moscosos_action(
        user_id=int(user["id"]),
        action="documentation_sent",
        entity_id=reservation_id,
        detail=(
            f"Documentación enviada: {reservation.reservation_date.isoformat()} "
            f"· {filename}"
        ),
    )
    return RedirectResponse(_reservar_url("doc_sent"), status_code=303)

