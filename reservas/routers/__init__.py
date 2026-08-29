from __future__ import annotations

from datetime import date, timedelta

from utils.time_madrid import today_madrid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth import load_user_dep
from context import ctx
from db.reservas_access import accept_reservas_normas, has_accepted_reservas_normas
from reservas.db import (
    get_user_other_room_same_slot,
    has_conflict_for_new_recurring,
    get_conflict_holder,
    user_has_double_room_in_recurring_range,
    list_recurring_for_range,
    recurring_applies_on,
    ROOMS,
    RESERVA_SLOTS,
    create_recurring,
    create_reservation,
    delete_recurring,
    delete_reservation,
    delete_reservations_range,
    get_reservation_by_id,
    build_week_nav,
    course_bounds_for_week,
    get_week_bounds,
    list_recurring,
    list_reservations_filtered,
    list_reservations_range,
    parse_reservar_prefill,
    resolve_reservation_date,
)
from aula_informatica.aulas_data import (
    get_aula_id_from_reservation_room,
    VALID_CLASS_HOURS as AI_VALID_CLASS_HOURS,
)
from db.aula_informatica_reports import has_report_for_session
from db.school_calendar import default_academic_year_start, get_latest_calendar
from db.groups import list_groups
from db.users import get_all_active_users_basic, get_all_teachers, get_user_by_id
from reservas.calendar import is_school_day
from utils.enums import (
    ROLE_ADMIN,
    ROLE_DIRECTOR,
    ROLE_JEFE,
    ROLE_PROFESOR,
    ROLE_SECRETARIO,
    PERM_RESERVAS_BORRADO_RANGO,
    PERM_RESERVAS_CUADRANTES,
    PERM_RESERVAS_DASHBOARD,
    PERM_RESERVAS_RECURRENTES,
    PERM_RESERVAS_RESERVAR,
    PERM_RESERVAS_RASTREAR,
    PERM_RESERVAS_VER_RESERVAS,
)
from utils.permissions import has_permission

router = APIRouter(prefix="/reservas", tags=["reservas"])


def _templates(request: Request):
    return request.app.state.templates


def _require(user: dict, perm: str) -> None:
    if not has_permission(user, perm):
        raise HTTPException(status_code=403)


def _is_privileged(user: dict) -> bool:
    return user.get("role") in {ROLE_ADMIN, ROLE_SECRETARIO}


def _can_reserve_multiple_rooms_same_slot(user: dict) -> bool:
    """Secretario, jefe, director y admin pueden reservar dos aulas en la misma franja."""
    return user.get("role") in {
        ROLE_ADMIN,
        ROLE_JEFE,
        ROLE_DIRECTOR,
        ROLE_SECRETARIO,
    }


def _max_date_for_user(user: dict, base: date) -> date | None:
    if _is_privileged(user):
        return None
    return base + timedelta(days=7)


def _default_course_bounds(today: date | None = None) -> tuple[date, date]:
    cal = get_latest_calendar()
    if cal and cal.get("first_date") and cal.get("last_day"):
        return cal["first_date"], cal["last_day"]

    start = default_academic_year_start(today)
    # Fallback habitual de curso: hasta el 30 de junio del año siguiente.
    end = date(start.year + 1, 6, 30)
    return start, end


def _reservar_prefill_url(reservation_date: str, room: str, slot: str) -> str:
    # quote (no '+') evita que "Informática A" llegue como "Informática+A" sin decodificar
    return (
        f"/reservas/reservar?reservation_date={quote(reservation_date, safe='')}"
        f"&room={quote(room, safe='')}"
        f"&slot={quote(slot, safe='')}"
    )


def _resolve_group(value: str | None) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    groups = list_groups()
    by_norm = {g.strip().lower(): g for g in groups}
    return by_norm.get(raw.lower())


@router.get("/dashboard", response_class=HTMLResponse)
def reservas_dashboard(request: Request, user: dict = Depends(load_user_dep)):
    _require(user, PERM_RESERVAS_DASHBOARD)
    return _templates(request).TemplateResponse(
        "reservas/dashboard.html",
        ctx(request, user=user, title="Reserva de aulas", privileged=_is_privileged(user)),
    )


@router.get("/normas-uso", response_class=HTMLResponse)
def reservas_normas_uso(request: Request, user: dict = Depends(load_user_dep)):
    _require(user, PERM_RESERVAS_DASHBOARD)
    accepted = has_accepted_reservas_normas(user_id=int(user["id"]))
    return _templates(request).TemplateResponse(
        "reservas/normas_uso.html",
        ctx(
            request,
            user=user,
            title="Normas de uso",
            normas_accepted=accepted,
            normas_pending=not accepted,
        ),
    )


@router.post("/normas-uso/aceptar")
def reservas_normas_aceptar(user: dict = Depends(load_user_dep)):
    _require(user, PERM_RESERVAS_DASHBOARD)
    accept_reservas_normas(user_id=int(user["id"]))
    return RedirectResponse("/reservas/dashboard", status_code=303)


@router.get("/cuadrantes", response_class=HTMLResponse)
def reservas_cuadrantes(
    request: Request,
    week_start: str | None = None,
    user: dict = Depends(load_user_dep),
):
    _require(user, PERM_RESERVAS_CUADRANTES)

    today = today_madrid()
    try:
        day = date.fromisoformat(week_start) if week_start else today
    except Exception:
        day = today

    start, end = get_week_bounds(day)
    course_start, course_end = course_bounds_for_week(start)
    week_nav = build_week_nav(
        start,
        school_first=course_start,
        school_last=course_end,
    )
    rows = list_reservations_range(start=start, end=end)
    recurring_rows = list_recurring_for_range(start=start, end=end)

    # index: room -> slot -> day_iso -> reservation
    slots = list(RESERVA_SLOTS)
    days = [start + timedelta(days=i) for i in range(5)]
    grid: dict = {room: {slot: {d.isoformat(): None for d in days} for slot in slots} for room in ROOMS}
    user_cache: dict[int, dict | None] = {}

    def _display_alias_or_name(reserved_for_user_id: int | None, fallback_name: str) -> str:
        if not reserved_for_user_id:
            return fallback_name
        uid = int(reserved_for_user_id)
        if uid not in user_cache:
            user_cache[uid] = get_user_by_id(uid)
        u = user_cache[uid] or {}
        alias = (u.get("alias") or "").strip() if isinstance(u, dict) else ""
        return alias or fallback_name

    for r in rows:
        d_iso = r["reservation_date"].isoformat()
        if r["room"] in grid and r["slot"] in grid[r["room"]] and d_iso in grid[r["room"]][r["slot"]]:
            r["reserved_for_display"] = _display_alias_or_name(
                r.get("reserved_for_user_id"),
                str(r.get("reserved_for_name") or ""),
            )
            grid[r["room"]][r["slot"]][d_iso] = r

    # Recurrentes como ocupación base (si no hay puntual)
    for rec in recurring_rows:
        room = rec["room"]
        slot = rec["slot"]
        if room not in grid or slot not in grid[room]:
            continue
        for d in days:
            d_iso = d.isoformat()
            if grid[room][slot][d_iso] is None and recurring_applies_on(rec, d):
                grid[room][slot][d_iso] = {
                    "reserved_for_display": _display_alias_or_name(
                        rec.get("reserved_for_user_id"),
                        str(rec.get("reserved_for_name") or ""),
                    ),
                    "is_recurring": True,
                }

    return _templates(request).TemplateResponse(
        "reservas/cuadrantes.html",
        ctx(
            request,
            user=user,
            title="Cuadrantes",
            rooms=ROOMS,
            slots=slots,
            days=days,
            grid=grid,
            week_start=start.isoformat(),
            week_end=end.isoformat(),
            week_nav=week_nav,
        ),
    )


@router.get("/reservar", response_class=HTMLResponse)
def reservas_reservar_form(
    request: Request,
    user: dict = Depends(load_user_dep),
    reservation_date: Annotated[str | None, Query()] = None,
    room: Annotated[str | None, Query()] = None,
    slot: Annotated[str | None, Query()] = None,
):
    _require(user, PERM_RESERVAS_RESERVAR)
    teachers = get_all_teachers() if _is_privileged(user) else []
    groups = list_groups()
    prefill_date, prefill_room, prefill_slot = parse_reservar_prefill(
        request,
        reservation_date=reservation_date,
        room=room,
        slot=slot,
    )
    if not prefill_date:
        raw_qp = (request.query_params.get("reservation_date") or "").strip()
        if raw_qp:
            prefill_date = resolve_reservation_date(raw_qp)
    return _templates(request).TemplateResponse(
        "reservas/reservar.html",
        ctx(
            request,
            user=user,
            title="Hacer reserva",
            rooms=ROOMS,
            slots=RESERVA_SLOTS,
            teachers=teachers,
            groups=groups,
            privileged=_is_privileged(user),
            today=today_madrid().isoformat(),
            prefill_date=prefill_date or today_madrid().isoformat(),
            prefill_room=prefill_room,
            prefill_slot=prefill_slot,
        ),
    )


@router.post("/reservar")
def reservas_reservar_post(
    request: Request,
    user: dict = Depends(load_user_dep),
    reservation_date: str = Form(...),
    grupo: str = Form(...),
    room: str = Form(...),
    slot: str = Form(...),
    teacher_id: str | None = Form(None),
    notes: str | None = Form(None),
):
    _require(user, PERM_RESERVAS_RESERVAR)

    try:
        d = date.fromisoformat(reservation_date)
    except Exception:
        return RedirectResponse("/reservas/reservar?status=error", status_code=303)

    group_name = _resolve_group(grupo)
    if room not in ROOMS or slot not in RESERVA_SLOTS or not group_name:
        return RedirectResponse("/reservas/reservar?status=error", status_code=303)

    if d < today_madrid():
        return RedirectResponse("/reservas/reservar?status=past", status_code=303)

    if not is_school_day(d):
        return RedirectResponse("/reservas/reservar?status=no_class", status_code=303)

    max_d = _max_date_for_user(user, today_madrid())
    if max_d is not None and d > max_d:
        return RedirectResponse("/reservas/reservar?status=too_far", status_code=303)

    # quién es el "reservado para"
    teacher_id_int = int(teacher_id) if teacher_id and teacher_id.strip().isdigit() else None

    if _is_privileged(user) and teacher_id_int:
        target = get_user_by_id(teacher_id_int)
        if not target or target.get("role") != "profesor":
            return RedirectResponse("/reservas/reservar?status=error", status_code=303)
        reserved_for_user_id = target["id"]
        reserved_for_name = target["name"]
    else:
        reserved_for_user_id = user["id"]
        reserved_for_name = user["name"]

    conflict = get_conflict_holder(room=room, d=d, slot=slot)
    if conflict:
        target_user = get_user_by_id(int(conflict["reserved_for_user_id"])) if conflict.get("reserved_for_user_id") else None
        alias = ((target_user or {}).get("alias") or "").strip() if isinstance(target_user, dict) else ""
        fallback = str(conflict.get("reserved_for_name") or "").strip() or "otro profesor"
        by_display = alias or fallback
        return RedirectResponse(
            f"/reservas/reservar?status=occupied&by={quote(by_display)}",
            status_code=303,
        )

    reserved_for = get_user_by_id(int(reserved_for_user_id))
    if (
        not _can_reserve_multiple_rooms_same_slot(user)
        and reserved_for
        and reserved_for.get("role") == ROLE_PROFESOR
    ):
        other_room = get_user_other_room_same_slot(
            reserved_for_user_id=int(reserved_for_user_id),
            d=d,
            slot=slot,
            exclude_room=room,
        )
        if other_room:
            return RedirectResponse(
                "/reservas/reservar?"
                f"status=double_room&room={quote(str(other_room['room']))}",
                status_code=303,
            )

    try:
        reservation_id = create_reservation(
            grupo=group_name,
            room=room,
            reservation_date=d,
            slot=slot,
            reserved_for_user_id=reserved_for_user_id,
            reserved_for_name=reserved_for_name,
            created_by_user_id=user["id"],
            notes=(notes or "").strip() or None,
        )
        log_reservation_action(
            user_id=user.get("id"),
            action="reservation_create",
            entity_id=reservation_id,
            detail=f"Reserva: {room} · {group_name} · {d.isoformat()} · {slot}",
        )
    except Exception:
        conflict = get_conflict_holder(room=room, d=d, slot=slot)
        if conflict:
            target_user = get_user_by_id(int(conflict["reserved_for_user_id"])) if conflict.get("reserved_for_user_id") else None
            alias = ((target_user or {}).get("alias") or "").strip() if isinstance(target_user, dict) else ""
            fallback = str(conflict.get("reserved_for_name") or "").strip() or "otro profesor"
            by_display = alias or fallback
            return RedirectResponse(
                f"/reservas/reservar?status=occupied&by={quote(by_display)}",
                status_code=303,
            )
        return RedirectResponse("/reservas/reservar?status=occupied", status_code=303)

    return RedirectResponse("/reservas/mis-reservas?status=created", status_code=303)


@router.get("/mis-reservas", response_class=HTMLResponse)
def reservas_mis_reservas(request: Request, user: dict = Depends(load_user_dep)):
    _require(user, PERM_RESERVAS_VER_RESERVAS)
    privileged = _is_privileged(user)
    qp = request.query_params
    room = qp.get("room") or None
    grupo_raw = qp.get("grupo") or None
    from_raw = qp.get("from_") or None
    to_raw = qp.get("to") or None
    teacher_raw = qp.get("teacher_id") or None

    course_start, course_end = _default_course_bounds()

    try:
        if from_raw:
            start = date.fromisoformat(from_raw)
        else:
            start = course_start if privileged else (today_madrid() - timedelta(days=30))
    except Exception:
        start = course_start if privileged else (today_madrid() - timedelta(days=30))
    try:
        if to_raw:
            end = date.fromisoformat(to_raw)
        else:
            end = course_end if privileged else None
    except Exception:
        end = course_end if privileged else None

    teachers = get_all_teachers() if privileged else []
    groups = list_groups()
    group_name = _resolve_group(grupo_raw)
    teacher_id = int(teacher_raw) if (privileged and teacher_raw and teacher_raw.isdigit()) else None

    rows = list_reservations_filtered(
        user_id=None if privileged else user["id"],
        start=start,
        end=end,
        room=room if room in ROOMS else None,
        grupo=group_name,
        reserved_for_user_id=teacher_id,
    )
    return _templates(request).TemplateResponse(
        "reservas/mis_reservas.html",
        ctx(
            request,
            user=user,
            title="Ver reservas" if privileged else "Mis reservas",
            rows=rows,
            privileged=privileged,
            rooms=ROOMS,
            groups=groups,
            teachers=teachers,
            filters={
                "grupo": group_name or "",
                "room": room or "",
                "from_": start.isoformat() if start else "",
                "to": end.isoformat() if end else "",
                "teacher_id": str(teacher_id or ""),
            },
        ),
    )


@router.post("/mis-reservas/delete/{reservation_id}")
def reservas_delete_reserva(
    reservation_id: int,
    user: dict = Depends(load_user_dep),
):
    _require(user, PERM_RESERVAS_VER_RESERVAS)
    row = get_reservation_by_id(reservation_id=reservation_id)
    if not row:
        return RedirectResponse("/reservas/mis-reservas?status=deleted", status_code=303)
    if int(row["reserved_for_user_id"]) != int(user["id"]) and not _is_privileged(user):
        raise HTTPException(status_code=403)
    delete_reservation(reservation_id=reservation_id)
    log_reservation_action(
        user_id=user.get("id"),
        action="reservation_delete",
        entity_id=reservation_id,
        detail=(
            f"Reserva eliminada: {row.get('room')} · {row.get('grupo')} · "
            f"{row.get('reservation_date')} · {row.get('slot')}"
        ),
    )
    return RedirectResponse("/reservas/mis-reservas?status=deleted", status_code=303)


@router.get("/recurrentes", response_class=HTMLResponse)
def reservas_recurrentes(request: Request, user: dict = Depends(load_user_dep)):
    _require(user, PERM_RESERVAS_RECURRENTES)
    users = get_all_active_users_basic()
    groups = list_groups()
    rows = list_recurring()
    default_start, default_end = _default_course_bounds()
    return _templates(request).TemplateResponse(
        "reservas/recurrentes.html",
        ctx(
            request,
            user=user,
            title="Recurrentes",
            rooms=ROOMS,
            slots=RESERVA_SLOTS,
            users=users,
            groups=groups,
            rows=rows,
            weekdays=[
                (0, "Lunes"),
                (1, "Martes"),
                (2, "Miércoles"),
                (3, "Jueves"),
                (4, "Viernes"),
            ],
            weekday_labels={
                0: "Lunes",
                1: "Martes",
                2: "Miércoles",
                3: "Jueves",
                4: "Viernes",
            },
            default_start_date=default_start.isoformat(),
            default_end_date=default_end.isoformat(),
        ),
    )


@router.post("/recurrentes")
def reservas_recurrentes_post(
    user: dict = Depends(load_user_dep),
    grupo: str = Form(...),
    room: str = Form(...),
    weekday: int = Form(...),
    slot: str = Form(...),
    start_date: str = Form(...),
    end_date: str | None = Form(None),
    user_id: int = Form(...),
    notes: str | None = Form(None),
):
    _require(user, PERM_RESERVAS_RECURRENTES)

    group_name = _resolve_group(grupo)
    if room not in ROOMS or slot not in RESERVA_SLOTS or weekday not in (0, 1, 2, 3, 4) or not group_name:
        return RedirectResponse("/reservas/recurrentes?status=error", status_code=303)

    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date) if end_date else None
    except Exception:
        return RedirectResponse("/reservas/recurrentes?status=error", status_code=303)
    today = today_madrid()
    effective_start = max(sd, today)

    if ed is not None and ed < effective_start:
        return RedirectResponse("/reservas/recurrentes?status=error", status_code=303)

    target = get_user_by_id(int(user_id))
    if not target or not target.get("active"):
        return RedirectResponse("/reservas/recurrentes?status=error", status_code=303)

    if has_conflict_for_new_recurring(
        room=room,
        weekday=weekday,
        slot=slot,
        start_date=effective_start,
        end_date=ed,
    ):
        return RedirectResponse("/reservas/recurrentes?status=occupied", status_code=303)

    if (
        not _can_reserve_multiple_rooms_same_slot(user)
        and target.get("role") == ROLE_PROFESOR
    ):
        double = user_has_double_room_in_recurring_range(
            reserved_for_user_id=int(target["id"]),
            weekday=weekday,
            slot=slot,
            exclude_room=room,
            start_date=effective_start,
            end_date=ed,
        )
        if double:
            return RedirectResponse(
                "/reservas/recurrentes?"
                f"status=double_room&room={quote(str(double['room']))}",
                status_code=303,
            )

    recurring_id = create_recurring(
        grupo=group_name,
        room=room,
        weekday=weekday,
        slot=slot,
        start_date=effective_start,
        end_date=ed,
        reserved_for_user_id=target["id"],
        reserved_for_name=target["name"],
        created_by_user_id=user["id"],
        notes=(notes or "").strip() or None,
    )
    log_reservation_action(
        user_id=user.get("id"),
        action="reservation_recurring_create",
        entity="reservation_recurring",
        entity_id=recurring_id,
        detail=(
            f"Recurrente: {room} · {group_name} · día {weekday} · {slot} · "
            f"desde {effective_start.isoformat()}"
        ),
    )

    return RedirectResponse("/reservas/recurrentes?status=created", status_code=303)


@router.post("/recurrentes/delete/{recurring_id}")
def reservas_recurrentes_delete(recurring_id: int, user: dict = Depends(load_user_dep)):
    _require(user, PERM_RESERVAS_RECURRENTES)
    delete_recurring(recurring_id=recurring_id)
    log_reservation_action(
        user_id=user.get("id"),
        action="reservation_recurring_delete",
        entity="reservation_recurring",
        entity_id=recurring_id,
        detail=f"Recurrente eliminada (id {recurring_id})",
    )
    return RedirectResponse("/reservas/recurrentes?status=deleted", status_code=303)


@router.get("/borrado-rango", response_class=HTMLResponse)
def reservas_borrado_rango(request: Request, user: dict = Depends(load_user_dep)):
    _require(user, PERM_RESERVAS_BORRADO_RANGO)
    return _templates(request).TemplateResponse(
        "reservas/borrado_rango.html",
        ctx(request, user=user, title="Borrado por rango", rooms=ROOMS),
    )


@router.post("/borrado-rango")
def reservas_borrado_rango_post(
    user: dict = Depends(load_user_dep),
    start_date: str = Form(...),
    end_date: str = Form(...),
    room: str | None = Form(None),
):
    _require(user, PERM_RESERVAS_BORRADO_RANGO)

    try:
        sd = date.fromisoformat(start_date)
        ed = date.fromisoformat(end_date)
    except Exception:
        return RedirectResponse("/reservas/borrado-rango?status=error", status_code=303)

    rooms = [room] if room and room in ROOMS else None
    deleted = delete_reservations_range(start=sd, end=ed, rooms=rooms)
    room_label = room if rooms else "todas las aulas"
    log_reservation_action(
        user_id=user.get("id"),
        action="reservation_range_delete",
        detail=f"Borrado por rango: {deleted} reserva(s) · {sd.isoformat()}–{ed.isoformat()} · {room_label}",
    )
    return RedirectResponse(f"/reservas/borrado-rango?status=ok&deleted={deleted}", status_code=303)


def _format_reservation_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _relleno_estado_display(row: dict) -> str:
    room = str(row.get("room") or "").strip()
    aula_id = get_aula_id_from_reservation_room(room)
    reservation_date = row.get("reservation_date")
    slot = str(row.get("slot") or "").strip()
    user_id = row.get("reserved_for_user_id")
    if not aula_id or not reservation_date or slot not in AI_VALID_CLASS_HOURS:
        return "—"
    if user_id is None:
        return "—"
    tiene = has_report_for_session(
        user_id=int(user_id),
        aula_id=aula_id,
        session_date=reservation_date,
        class_hour=slot,
    )
    return "Sí" if tiene else "No"


def _rastrear_rows_punctual(rows: list[dict]) -> list[dict]:
    payload: list[dict] = []
    for row in rows:
        reservation_date = row.get("reservation_date")
        relleno = _relleno_estado_display(row)
        payload.append(
            {
                "fecha_display": (
                    _format_reservation_date(reservation_date)
                    if reservation_date
                    else "—"
                ),
                "slot": str(row.get("slot") or "—"),
                "reserved_for_name": str(row.get("reserved_for_name") or "—"),
                "grupo": str(row.get("grupo") or "—").strip() or "—",
                "room": str(row.get("room") or "—"),
                "relleno_estado": relleno,
            }
        )
    return payload


@router.get("/rastrear", response_class=HTMLResponse)
def reservas_rastrear(request: Request, user: dict = Depends(load_user_dep)):
    _require(user, PERM_RESERVAS_RASTREAR)
    teachers = get_all_teachers()
    return _templates(request).TemplateResponse(
        "reservas/rastrear.html",
        ctx(
            request,
            user=user,
            title="Rastrear",
            rooms=ROOMS,
            teachers=teachers,
        ),
    )


@router.get("/rastrear/aula-reservas", response_class=JSONResponse)
def reservas_rastrear_aula_reservas(
    room: str = Query(""),
    user: dict = Depends(load_user_dep),
):
    _require(user, PERM_RESERVAS_RASTREAR)
    room_name = (room or "").strip()
    if room_name not in ROOMS:
        return JSONResponse([])
    rows = list_reservations_filtered(room=room_name)
    return JSONResponse(_rastrear_rows_punctual(rows))


@router.get("/rastrear/profesor-reservas", response_class=JSONResponse)
def reservas_rastrear_profesor_reservas(
    profesor_id: int = Query(0),
    user: dict = Depends(load_user_dep),
):
    _require(user, PERM_RESERVAS_RASTREAR)
    if int(profesor_id) <= 0:
        return JSONResponse([])
    teacher = get_user_by_id(int(profesor_id))
    if not teacher:
        return JSONResponse([])
    rows = list_reservations_filtered(reserved_for_user_id=int(profesor_id))
    return JSONResponse(_rastrear_rows_punctual(rows))
