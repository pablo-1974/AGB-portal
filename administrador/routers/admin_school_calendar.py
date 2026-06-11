"""Administración del calendario escolar (portal general)."""

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import load_user_dep
from context import ctx
from db.moscosos_calendar import recalculate_moscosos_after_school_calendar_change
from db.school_calendar import (
    STAGE_END_LABELS,
    build_calendar_months,
    get_calendar_by_id,
    get_latest_calendar,
    save_school_calendar,
    set_other_holidays,
    stage_end_legend_items,
)

from utils.enums import PERM_CALENDARIO_ESCOLAR
from utils.permissions import has_permission

router = APIRouter(prefix="/admin/calendar", tags=["admin_calendar"])


def _templates(request: Request):
    return request.app.state.templates


def _require_calendar_perm(user: dict) -> None:
    if not has_permission(user, PERM_CALENDARIO_ESCOLAR):
        raise HTTPException(status_code=403)


def _parse_optional_date(value: str) -> date | None:
    clean = (value or "").strip()
    if not clean:
        return None
    return date.fromisoformat(clean)


def _format_optional_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else "—"


def _build_saved_summary(cal: dict) -> str:
    parts: list[str] = []
    for key, label in STAGE_END_LABELS:
        d = cal.get(key)
        if d:
            parts.append(f"{label}={_format_optional_date(d)}")
    return "; ".join(parts) if parts else "Fechas generales guardadas"


@router.get("/")
def calendar_root(user=Depends(load_user_dep)):
    _require_calendar_perm(user)
    return RedirectResponse("/admin/calendar/edit", status_code=303)


@router.post("/")
def calendar_root_post(user=Depends(load_user_dep)):
    _require_calendar_perm(user)
    return RedirectResponse("/admin/calendar/edit", status_code=303)


@router.get("/view", response_class=HTMLResponse)
def calendar_view(request: Request, user=Depends(load_user_dep)):
    _require_calendar_perm(user)
    cal = get_latest_calendar()
    if not cal:
        return RedirectResponse("/admin/calendar/edit", status_code=303)
    months = build_calendar_months(cal)
    legend = stage_end_legend_items(cal)
    return _templates(request).TemplateResponse(
        "admin/calendar_view.html",
        ctx(
            request,
            user,
            title="Vista calendario escolar",
            calendar=cal,
            months=months,
            stage_end_legend=legend,
        ),
    )


@router.get("/edit", response_class=HTMLResponse)
def calendar_edit(
    request: Request,
    user=Depends(load_user_dep),
    saved: str | None = Query(default=None),
):
    _require_calendar_perm(user)
    cal = get_latest_calendar()
    flash_ok = bool(request.session.pop("calendar_saved_ok", False))
    query_ok = (saved or "").strip() == "1"
    calendar_saved = flash_ok or query_ok
    summary = ""
    if calendar_saved and cal:
        summary = _build_saved_summary(cal)
    flash_msg = str(request.session.pop("calendar_saved_msg", "") or "").strip()
    if flash_msg:
        summary = flash_msg
    return _templates(request).TemplateResponse(
        "admin/calendar_edit.html",
        ctx(
            request,
            user,
            title="Calendario escolar",
            calendar=cal,
            calendar_saved=calendar_saved,
            calendar_saved_summary=summary,
        ),
    )


@router.post("/edit", response_class=HTMLResponse)
def calendar_edit_post(
    request: Request,
    user=Depends(load_user_dep),
    school_year: str = Form(...),
    first_day: str = Form(...),
    last_day: str = Form(...),
    xmas_start: str = Form(...),
    xmas_end: str = Form(...),
    easter_start: str = Form(...),
    easter_end: str = Form(...),
    end_eso: str = Form(""),
    end_fpb1: str = Form(""),
    end_fpb2: str = Form(""),
    end_fpm1: str = Form(""),
    end_fpm2: str = Form(""),
    end_bach1: str = Form(""),
    end_bach2: str = Form(""),
):
    _require_calendar_perm(user)

    stage_ends = {
        "end_eso": _parse_optional_date(end_eso),
        "end_fpb1": _parse_optional_date(end_fpb1),
        "end_fpb2": _parse_optional_date(end_fpb2),
        "end_fpm1": _parse_optional_date(end_fpm1),
        "end_fpm2": _parse_optional_date(end_fpm2),
        "end_bach1": _parse_optional_date(end_bach1),
        "end_bach2": _parse_optional_date(end_bach2),
    }

    cal_id = save_school_calendar(
        school_year=school_year.strip(),
        first_date=date.fromisoformat(first_day.strip()),
        last_day=date.fromisoformat(last_day.strip()),
        xmas_start=date.fromisoformat(xmas_start.strip()),
        xmas_end=date.fromisoformat(xmas_end.strip()),
        easter_start=date.fromisoformat(easter_start.strip()),
        easter_end=date.fromisoformat(easter_end.strip()),
        **stage_ends,
    )
    recalculate_moscosos_after_school_calendar_change(cal_id)

    saved = get_calendar_by_id(cal_id) or {}
    for key, sent in stage_ends.items():
        if sent is None:
            continue
        got = saved.get(key)
        if got != sent:
            raise HTTPException(
                status_code=500,
                detail=f"No se guardó {key}: enviado {sent.isoformat()}, en BD {got}",
            )

    summary = _build_saved_summary(saved)
    return _templates(request).TemplateResponse(
        "admin/calendar_edit.html",
        ctx(
            request,
            user,
            title="Calendario escolar",
            calendar=saved,
            calendar_saved=True,
            calendar_saved_summary=summary,
        ),
        status_code=200,
    )


@router.post("/delete-holiday")
def calendar_delete_holiday(
    request: Request,
    user=Depends(load_user_dep),
    holiday_date: str = Form(...),
):
    _require_calendar_perm(user)
    cal = get_latest_calendar()
    if not cal:
        return RedirectResponse("/admin/calendar/edit", status_code=303)
    existing = list(cal.get("other_holidays") or [])
    new_list = [h for h in existing if h != holiday_date]
    set_other_holidays(cal["id"], new_list)
    recalculate_moscosos_after_school_calendar_change(int(cal["id"]))
    return RedirectResponse("/admin/calendar/edit", status_code=303)


@router.post("/add-holiday")
def calendar_add_holiday(
    request: Request,
    user=Depends(load_user_dep),
    holiday_date: str = Form(...),
):
    _require_calendar_perm(user)
    cal = get_latest_calendar()
    if not cal:
        return RedirectResponse("/admin/calendar/edit", status_code=303)
    new_date = holiday_date.strip()
    existing = list(cal.get("other_holidays") or [])
    if new_date not in existing:
        existing.append(new_date)
    set_other_holidays(cal["id"], existing)
    recalculate_moscosos_after_school_calendar_change(int(cal["id"]))
    return RedirectResponse("/admin/calendar/edit", status_code=303)
