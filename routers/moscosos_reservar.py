"""GET/POST /moscosos/reservar (incluye reservar para otro profesor)."""

from __future__ import annotations

from datetime import date, timedelta

from utils.time_madrid import today_madrid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from context import ctx
from db.action_logs import log_moscosos_action
from db.moscosos_calendar import (
    buffer_last_booking_date,
    max_booking_date,
    moscosos_calendar_bundle,
)
from db.moscosos_reservations import (
    MAX_RESERVATIONS_PER_USER_PER_COURSE,
    create_reservation,
    list_user_reservations,
)
from db.school_calendar import MES_ES
from db.users import get_all_teachers, get_user_by_id
from moscosos.booking import (
    TRIMESTER_NUM_LABEL,
    staff_other_booking_window,
    trimester_number_for_date,
    validate_new_reservation,
)
from moscosos.deps import require_moscosos_access
from utils.enums import PERM_MOSCOSOS_STAFF, ROLES_ADMINISTRATIVOS
from utils.permissions import has_permission

router = APIRouter(
    prefix="/moscosos",
    tags=["moscosos"],
    dependencies=[Depends(require_moscosos_access)],
)

MoscososUser = Annotated[dict, Depends(require_moscosos_access)]


def _can_book_for_others(user: dict) -> bool:
    if has_permission(user, PERM_MOSCOSOS_STAFF):
        return True
    role = str(user.get("role") or "").strip().lower()
    return role in ROLES_ADMINISTRATIVOS


def _format_date_es(d: date) -> str:
    return f"{d.day} de {MES_ES[d.month].lower()} de {d.year}"


def _reservar_url(status: str, profesor_id: int | None = None) -> str:
    url = f"/moscosos/reservar?status={status}"
    if profesor_id:
        url += f"&profesor={int(profesor_id)}"
    return url


def _reservar_context(request: Request, user: dict, bundle: dict | None, today: date):
    can_book_for_others = _can_book_for_others(user)
    selected_profesor = (request.query_params.get("profesor") or "").strip()
    selected_profesor_name = None
    if selected_profesor.isdigit():
        other = get_user_by_id(int(selected_profesor))
        if other and int(other.get("active") or 0) == 1:
            selected_profesor_name = (other.get("name") or "").strip()
        else:
            selected_profesor = ""
    if not bundle:
        return {
            "calendar_ready": False,
            "mis_reservas": [],
            "reservas_cupo_usado": 0,
            "reservas_cupo_max": MAX_RESERVATIONS_PER_USER_PER_COURSE,
            "puede_reservar": False,
            "can_book_for_others": can_book_for_others,
            "profesores_reserva": [],
            "selected_profesor": selected_profesor,
            "selected_profesor_name": selected_profesor_name,
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
    staff_min, staff_max = staff_other_booking_window(today, bundle)
    prefill_raw = (request.query_params.get("fecha") or "").strip()
    prefill_date = None
    prefill_display = None
    if prefill_raw:
        try:
            prefill_d = date.fromisoformat(prefill_raw)
            in_self = first_bookable <= prefill_d <= last_bookable
            in_staff = can_book_for_others and staff_min <= prefill_d <= staff_max
            if in_self or in_staff:
                prefill_date = prefill_raw
                prefill_display = _format_date_es(prefill_d)
        except ValueError:
            pass
    profesores = []
    if can_book_for_others:
        self_id = int(user["id"])
        profesores = [
            {"id": int(t["id"]), "name": str(t.get("name") or "").strip()}
            for t in get_all_teachers()
            if int(t["id"]) != self_id and str(t.get("name") or "").strip()
        ]
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
        "staff_min_date": staff_min.isoformat(),
        "staff_max_date": staff_max.isoformat(),
        "staff_min_display": _format_date_es(staff_min),
        "staff_max_display": _format_date_es(staff_max),
        "prefill_date": prefill_date,
        "prefill_display": prefill_display,
        "first_bookable_display": _format_date_es(first_bookable),
        "last_bookable_display": _format_date_es(last_bookable),
        "can_book_for_others": can_book_for_others,
        "profesores_reserva": profesores,
        "selected_profesor": selected_profesor,
        "selected_profesor_name": selected_profesor_name,
    }


@router.get("/reservar", response_class=HTMLResponse)
def moscosos_reservar_form(request: Request, user: MoscososUser):
    today = today_madrid()
    bundle = moscosos_calendar_bundle()
    return request.app.state.templates.TemplateResponse(
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
    teacher_id: str = Form(""),
):
    today = today_madrid()
    bundle = moscosos_calendar_bundle()
    if not bundle:
        return RedirectResponse(_reservar_url("error"), status_code=303)

    try:
        d = date.fromisoformat(reservation_date.strip())
    except ValueError:
        return RedirectResponse(_reservar_url("error"), status_code=303)

    target_id = int(user["id"])
    for_other = False
    raw_tid = (teacher_id or "").strip()
    if raw_tid and _can_book_for_others(user):
        if not raw_tid.isdigit():
            return RedirectResponse(_reservar_url("error"), status_code=303)
        tid = int(raw_tid)
        if tid != target_id:
            other = get_user_by_id(tid)
            if not other or int(other.get("active") or 0) != 1:
                return RedirectResponse(_reservar_url("error"), status_code=303)
            target_id = tid
            for_other = True

    err = validate_new_reservation(
        user_id=target_id,
        reservation_date=d,
        today=today,
        bundle=bundle,
        skip_booking_window=for_other,
        for_other=for_other,
    )
    redirect_prof = target_id if for_other else None
    if err:
        return RedirectResponse(
            _reservar_url(err.code, profesor_id=redirect_prof), status_code=303
        )

    trimester = trimester_number_for_date(
        d,
        bundle["calendar"],
        bundle["excluded"],
        course_start=bundle.get("course_start_date"),
        course_end=bundle.get("course_end_date"),
    )
    if trimester is None:
        return RedirectResponse(
            _reservar_url("not_bookable", profesor_id=redirect_prof), status_code=303
        )

    created = create_reservation(
        school_calendar_id=int(bundle["calendar"]["id"]),
        user_id=target_id,
        reservation_date=d,
        trimester=trimester,
    )
    if created is None:
        return RedirectResponse(
            _reservar_url("day_full", profesor_id=redirect_prof), status_code=303
        )

    detail = (
        f"Reserva moscoso: {d.isoformat()} · trimestre {trimester} · plaza {created.slot}"
    )
    if for_other:
        detail += f" · para usuario #{target_id}"
    log_moscosos_action(
        user_id=int(user["id"]),
        action="reservation_create",
        entity_id=int(created.id),
        detail=detail,
    )
    return RedirectResponse(
        _reservar_url("created", profesor_id=redirect_prof), status_code=303
    )
