"""Administración del calendario de moscosos (derivado del calendario escolar)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import load_user_dep
from context import ctx
from db.moscosos_calendar import (
    BUFFER_SCHOOL_DAYS_DEFAULT,
    COURSE_EDGE_SCHOOL_DAYS,
    build_moscosos_calendar_months,
    get_config_for_calendar,
    moscosos_calendar_bundle,
    set_course_edge_dates,
    set_extra_excluded_dates,
)
from db.school_calendar import get_latest_calendar
from utils.enums import PERM_CALENDARIO_MOSCOSOS
from utils.permissions import has_permission

router = APIRouter(prefix="/admin/moscosos/calendar", tags=["admin_moscosos_calendar"])


def _templates(request: Request):
    return request.app.state.templates


def _require_perm(user: dict) -> None:
    if not has_permission(user, PERM_CALENDARIO_MOSCOSOS):
        raise HTTPException(status_code=403)


@router.get("/", response_class=HTMLResponse)
def moscosos_calendar_home(request: Request, user: dict = Depends(load_user_dep)):
    _require_perm(user)
    bundle = moscosos_calendar_bundle()
    if not bundle:
        return RedirectResponse("/admin/calendar/edit", status_code=303)

    cal = bundle["calendar"]
    months = build_moscosos_calendar_months(
        cal,
        bundle["excluded"],
        buffer_days=bundle["buffer_days"],
        course_start=bundle.get("course_start_date"),
        course_end=bundle.get("course_end_date"),
    )
    cs = bundle.get("course_start_date")
    ce = bundle.get("course_end_date")
    return _templates(request).TemplateResponse(
        "admin/moscosos_calendar.html",
        ctx(
            request,
            user,
            title="Calendario de moscosos",
            portal_shell_title="Gestión calendario moscosos",
            calendar=cal,
            months=months,
            buffer_days=bundle["buffer_days"],
            buffer_dates=bundle["buffer_dates"],
            course_edge_days=bundle.get("course_edge_days", COURSE_EDGE_SCHOOL_DAYS),
            course_start_date=cs.isoformat() if cs else "",
            course_end_date=ce.isoformat() if ce else "",
            course_start_dates=bundle.get("course_start_dates") or [],
            course_end_dates=bundle.get("course_end_dates") or [],
            extra_dates=bundle["extra_dates"],
            buffer_default=BUFFER_SCHOOL_DAYS_DEFAULT,
        ),
    )


@router.post("/course-dates")
def moscosos_set_course_dates(
    request: Request,
    user: dict = Depends(load_user_dep),
    course_start: str = Form(...),
    course_end: str = Form(...),
):
    _require_perm(user)
    cal = get_latest_calendar()
    if not cal:
        return RedirectResponse("/admin/calendar/edit", status_code=303)

    try:
        start_d = date.fromisoformat(course_start.strip()[:10])
        end_d = date.fromisoformat(course_end.strip()[:10])
    except ValueError:
        return RedirectResponse("/admin/moscosos/calendar/?error=fecha", status_code=303)

    if end_d < start_d:
        return RedirectResponse("/admin/moscosos/calendar/?error=rango", status_code=303)

    set_course_edge_dates(int(cal["id"]), course_start=start_d, course_end=end_d)
    return RedirectResponse("/admin/moscosos/calendar/", status_code=303)


@router.post("/add-exclusion")
def moscosos_add_exclusion(
    request: Request,
    user: dict = Depends(load_user_dep),
    exclusion_date: str = Form(...),
):
    _require_perm(user)
    cal = get_latest_calendar()
    if not cal:
        return RedirectResponse("/admin/calendar/edit", status_code=303)

    new_date = exclusion_date.strip()[:10]
    try:
        date.fromisoformat(new_date)
    except ValueError:
        return RedirectResponse("/admin/moscosos/calendar/?error=fecha", status_code=303)

    cfg = get_config_for_calendar(int(cal["id"]))
    existing = list(cfg["extra_excluded_dates"])
    if new_date not in existing:
        existing.append(new_date)
        existing.sort()
    set_extra_excluded_dates(int(cal["id"]), existing)
    return RedirectResponse("/admin/moscosos/calendar/", status_code=303)


@router.post("/remove-exclusion")
def moscosos_remove_exclusion(
    request: Request,
    user: dict = Depends(load_user_dep),
    exclusion_date: str = Form(...),
):
    _require_perm(user)
    cal = get_latest_calendar()
    if not cal:
        return RedirectResponse("/admin/calendar/edit", status_code=303)

    target = exclusion_date.strip()[:10]
    cfg = get_config_for_calendar(int(cal["id"]))
    remaining = [d for d in cfg["extra_excluded_dates"] if d != target]
    set_extra_excluded_dates(int(cal["id"]), remaining)
    return RedirectResponse("/admin/moscosos/calendar/", status_code=303)
