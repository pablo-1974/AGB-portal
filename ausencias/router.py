from datetime import date, timedelta
from io import BytesIO

from utils.time_madrid import today_madrid

from utils.local_deps import ensure_local_deps

ensure_local_deps()
try:
    import openpyxl
except ImportError:
    openpyxl = None  # type: ignore[assignment]
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from psycopg.errors import UniqueViolation

from auth import load_user_dep
from context import ctx
from ausencias.db import (
    _date_ord,
    add_action_log,
    close_leave,
    create_leave_root,
    create_substitution,
    delete_absence,
    delete_leave_subtree,
    finalize_baja_leave,
    finalize_substitution_resignation,
    get_absence_by_id,
    get_leave_by_id,
    get_open_substitution_tip_teacher_id,
    list_absences_range,
    list_active_teachers,
    list_available_substitute_teachers,
    list_exprofes_for_substitution,
    list_leaves,
    list_open_parent_leaves_without_active_substitution,
    list_leaves_uncategorized_in_range,
    list_teachers_available_for_absence,
    list_teachers_eligible_substitution_resign_finish,
    update_absence_by_id,
    update_absence_category,
    update_leave_category,
    update_leave_record,
    update_substitution_leave_dates,
    upsert_absence,
)
from db.users import create_user_admin_returning_id, get_all_teachers, get_user_by_id
from utils.enums import PERM_AUSENCIAS_APP, PERM_BACKUP, ROLES_TODOS
from utils.permissions import has_permission
from utils.pdf_http import safe_pdf_filename
from ausencias.services.daily_report import build_daily_report_preview
from ausencias.services.monthly_report import build_monthly_report
from ausencias.services.pdf_daily import render_daily_report_pdf_bytes
from ausencias.services.pdf_monthly import render_monthly_report_pdf_bytes
from ausencias.services.stats_ranking import get_stats_ranking
from ausencias.services.stats_recount import STATS_CAUSA_CODES, get_stats_recount
from ausencias.absence_categories import ABSENCE_CATEGORIES, ALLOWED_ABSENCE_CATEGORY_CODES
from db.school_calendar import get_course_start_iso, get_latest_calendar
from reservas.calendar import is_school_day

router = APIRouter(prefix="/ausencias", tags=["ausencias"])
HOUR_LABELS = ("1ª", "2ª", "3ª", "Recreo", "4ª", "5ª", "6ª")
FULL_DAY_MASK = (1 << 7) - 1

_ABSENCES_RETURN_PATHS = frozenset(
    {
        "/ausencias/absences/manage",
        "/ausencias/absences/new",
        "/ausencias/absences/categorize",
    }
)


def _absences_redirect_url(redirect_base: str | None, from_: str | None, to: str | None) -> str:
    base = (redirect_base or "").strip() or "/ausencias/absences/manage"
    if base not in _ABSENCES_RETURN_PATHS:
        base = "/ausencias/absences/manage"
    q_from = (from_ or "").strip()
    q_to = (to or "").strip()
    if q_from and q_to:
        return f"{base}?from={q_from}&to={q_to}"
    return base


_LEAVES_CATEGORIZE_RETURN_PATHS = frozenset({"/ausencias/leaves/categorize"})


def _leaves_categorize_redirect_url(
    from_: str | None,
    to: str | None,
    redirect_base: str | None = None,
) -> str:
    base = (redirect_base or "").strip() or "/ausencias/leaves/categorize"
    if base not in _LEAVES_CATEGORIZE_RETURN_PATHS:
        base = "/ausencias/leaves/categorize"
    q_from = (from_ or "").strip()
    q_to = (to or "").strip()
    if q_from and q_to:
        return f"{base}?from={q_from}&to={q_to}"
    return base


_LEAVE_CLOSE_REDIRECTS = frozenset(
    {
        "/ausencias/leaves/manage",
        "/ausencias/leaves/finish",
        "/ausencias/substitutions/finish",
    }
)

_SUBSTITUTE_REDIRECTS = frozenset(
    {
        "/ausencias/leaves/manage",
        "/ausencias/substitutions/start",
        "/ausencias/leaves/substitutions",
    }
)


def _leave_close_redirect(next_: str | None) -> str:
    u = (next_ or "").strip()
    return u if u in _LEAVE_CLOSE_REDIRECTS else "/ausencias/leaves/manage"


def _substitute_redirect(next_: str | None) -> str:
    u = (next_ or "").strip()
    return u if u in _SUBSTITUTE_REDIRECTS else "/ausencias/leaves/substitutions"


def _stats_default_range() -> tuple[date, date]:
    """Rango por defecto como la app legacy (inicio de curso configurado → hoy)."""
    today = today_madrid()
    cal = get_latest_calendar()
    if cal and cal.get("first_date"):
        fd = cal["first_date"]
        if isinstance(fd, date):
            date_from = fd
        else:
            try:
                date_from = date.fromisoformat(str(fd)[:10])
            except ValueError:
                date_from = today
    else:
        date_from = today
    return date_from, today


def _stats_teacher_id_query(raw: str | None) -> int | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _stats_tipo_filter(raw: str | None) -> str:
    t = (raw or "both").strip().lower()
    return t if t in {"absences", "leaves", "both"} else "both"


def _parse_absence_range(
    from_: str | None,
    to: str | None,
    *,
    default_start: date,
    default_end: date,
) -> tuple[date, date, str, str]:
    start_s = (from_ or default_start.isoformat()).strip()
    end_s = (to or default_end.isoformat()).strip()
    try:
        start_d = date.fromisoformat(start_s)
        end_d = date.fromisoformat(end_s)
    except ValueError:
        start_d = default_start
        end_d = default_end
        start_s, end_s = start_d.isoformat(), end_d.isoformat()
    if start_d > end_d:
        start_d, end_d = end_d, start_d
        start_s, end_s = start_d.isoformat(), end_d.isoformat()
    return start_d, end_d, start_s, end_s


def _ensure_access(user: dict) -> bool:
    return has_permission(user, PERM_AUSENCIAS_APP)


def _can_manage_absence_records(user: dict) -> bool:
    return str(user.get("role") or "").strip().lower() in {"admin", "director"}


def _require_ausencias_app(user: dict) -> None:
    if not _ensure_access(user):
        raise HTTPException(status_code=403, detail="Sin permiso para Ausencias.")


def _require_manage_absence_records(user: dict) -> None:
    if not _can_manage_absence_records(user):
        raise HTTPException(status_code=403, detail="Sin permiso para catalogar o administrar ausencias.")


def _leave_date_iso(val) -> str | None:
    if val is None:
        return None
    if hasattr(val, "isoformat"):
        return val.isoformat()[:10]
    return str(val)[:10]


def _leave_kind_label(kind_raw: str | None) -> str:
    k = (kind_raw or "baja").strip().lower()
    return "Excedencia" if k == "excedencia" else "Baja"


def _leave_category_display(cat) -> str:
    c = (str(cat) if cat is not None else "").strip()
    return c if c else "—"


def _build_leave_list_items(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Misma idea que la vista `/leaves` de consultas: filas no sustitución y cadena de hijos directos."""
    by_parent: dict[int, list[dict]] = {}
    for r in rows:
        pid = r.get("parent_leave_id")
        if pid is not None:
            by_parent.setdefault(int(pid), []).append(r)
    for lst in by_parent.values():
        lst.sort(key=lambda x: (_date_ord(x["start_date"]), int(x["id"])))

    def chain_names(parent_id: int, *, parent_leave_active: bool) -> list[str]:
        chs = list(by_parent.get(parent_id, []))
        if parent_leave_active:
            chs = [ch for ch in chs if ch.get("end_date") is None]
        chs.sort(key=lambda x: (_date_ord(x["start_date"]), int(x["id"])))
        return [str(ch["teacher_name"] or "") for ch in chs]

    nonsub = [r for r in rows if not r.get("is_substitution")]
    active_items: list[dict] = []
    closed_items: list[dict] = []
    for lv in nonsub:
        sd = lv["start_date"]
        ed = lv["end_date"]
        sort_key = _leave_date_iso(sd) or ""
        cause_txt = str(lv.get("cause") or "").strip()
        parent_active = ed is None
        item = {
            "leave_id": int(lv["id"]),
            "teacher_name": str(lv.get("teacher_name") or ""),
            "start_date": sort_key,
            "end_date": _leave_date_iso(ed),
            "tipo": _leave_kind_label(lv.get("leave_kind")),
            "cause": cause_txt if cause_txt else "—",
            "catalogacion": _leave_category_display(lv.get("category")),
            "chain": chain_names(int(lv["id"]), parent_leave_active=parent_active),
            "_sort": sort_key,
        }
        if ed is None:
            active_items.append(item)
        else:
            closed_items.append(item)

    active_items.sort(key=lambda it: (it["_sort"], it["leave_id"]))
    closed_items.sort(key=lambda it: (it["_sort"], it["leave_id"]), reverse=True)
    return active_items, closed_items


def _hours_mask_from_form(mode: str, hour_from: int | None, hour_to: int | None) -> int | None:
    m = (mode or "all").strip().lower()
    if m == "all":
        return FULL_DAY_MASK
    if hour_from is None or hour_to is None:
        return None
    low = min(int(hour_from), int(hour_to))
    high = max(int(hour_from), int(hour_to))
    if low < 0 or high > 6:
        return None
    mask = 0
    for idx in range(low, high + 1):
        mask |= 1 << idx
    return mask


def _mode_and_hours_from_mask(mask: int) -> tuple[str, int, int]:
    if mask == FULL_DAY_MASK:
        return "all", 0, 6
    bits = [i for i in range(7) if (mask >> i) & 1]
    if not bits:
        return "all", 0, 6
    return "range", min(bits), max(bits)


def _mask_to_human(mask: int) -> str:
    if mask <= 0:
        return "-"
    on = [i for i in range(7) if (mask >> i) & 1]
    if not on:
        return "-"
    parts: list[str] = []
    start = on[0]
    prev = on[0]
    for idx in on[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        parts.append(HOUR_LABELS[start] if start == prev else f"{HOUR_LABELS[start]}-{HOUR_LABELS[prev]}")
        start = prev = idx
    parts.append(HOUR_LABELS[start] if start == prev else f"{HOUR_LABELS[start]}-{HOUR_LABELS[prev]}")
    return ", ".join(parts)


@router.get("/", include_in_schema=False)
def ausencias_root():
    return RedirectResponse("/ausencias/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
def ausencias_dashboard(request: Request, user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)

    return request.app.state.templates.TemplateResponse(
        "ausencias/dashboard.html",
        ctx(request, user=user, title="Ausencias"),
    )


@router.get("/stats", response_class=HTMLResponse)
def ausencias_stats_hub(request: Request, user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    return request.app.state.templates.TemplateResponse(
        "ausencias/stats_hub.html",
        ctx(
            request,
            user=user,
            title="Estadísticas",
            can_catalog_leaves=_can_manage_absence_records(user),
        ),
    )


@router.get("/stats/recount", response_class=HTMLResponse)
def ausencias_stats_recount_page(
    request: Request,
    user: dict = Depends(load_user_dep),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    teacher_id: str | None = Query(None),
    tipo: str = Query("both"),
    categoria: str = Query("ALL"),
):
    _require_ausencias_app(user)
    df0, dt0 = _stats_default_range()
    d_from = date_from or df0
    d_to = date_to or dt0
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    tipo_clean = _stats_tipo_filter(tipo)
    tid = _stats_teacher_id_query(teacher_id)
    cat_raw = (categoria or "ALL").strip().upper()
    cat_disp = "ALL"
    if cat_raw != "ALL" and cat_raw in STATS_CAUSA_CODES:
        cat_disp = cat_raw

    rows = get_stats_recount(
        date_from=d_from,
        date_to=d_to,
        teacher_id=tid,
        tipo=tipo_clean,
        categoria=cat_disp,
    )
    teachers = get_all_teachers()
    return request.app.state.templates.TemplateResponse(
        "ausencias/stats_recount.html",
        ctx(
            request,
            user=user,
            title="Estadísticas · Recuento",
            rows=rows,
            teachers=teachers,
            categorias=list(STATS_CAUSA_CODES),
            date_from=d_from.isoformat(),
            date_to=d_to.isoformat(),
            teacher_id=str(tid or ""),
            tipo=tipo_clean,
            categoria=cat_disp,
            can_catalog_leaves=_can_manage_absence_records(user),
        ),
    )


@router.get("/stats/ranking", response_class=HTMLResponse)
def ausencias_stats_ranking_page(
    request: Request,
    user: dict = Depends(load_user_dep),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    tipo: str = Query("both"),
):
    _require_ausencias_app(user)
    df0, dt0 = _stats_default_range()
    d_from = date_from or df0
    d_to = date_to or dt0
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    tipo_clean = _stats_tipo_filter(tipo)
    rows = get_stats_ranking(date_from=d_from, date_to=d_to, tipo=tipo_clean)
    return request.app.state.templates.TemplateResponse(
        "ausencias/stats_ranking.html",
        ctx(
            request,
            user=user,
            title="Estadísticas · Ranking",
            rows=rows,
            date_from=d_from.isoformat(),
            date_to=d_to.isoformat(),
            tipo=tipo_clean,
            can_catalog_leaves=_can_manage_absence_records(user),
        ),
    )


@router.get("/absences", response_class=HTMLResponse)
def ausencias_absences_hub(request: Request, user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    return request.app.state.templates.TemplateResponse(
        "ausencias/absences.html",
        ctx(
            request,
            user=user,
            title="Ausencias",
            can_catalog_absences=_can_manage_absence_records(user),
        ),
    )


def _absences_rows_for_range(start_d: date, end_d: date, *, uncategorized_only: bool = False) -> list[dict]:
    rows = list_absences_range(
        from_date=start_d,
        to_date=end_d,
        uncategorized_only=uncategorized_only,
    )
    for row in rows:
        row["hours_human"] = _mask_to_human(int(row.get("hours_mask") or 0))
    return rows


def _template_absences_new(
    request: Request,
    user: dict,
    *,
    target_day: date,
    form_error: str | None = None,
):
    today = today_madrid()
    course_start = date.fromisoformat(get_course_start_iso(today))
    start_d, end_d, summary_from_s, summary_to_s = _parse_absence_range(
        None, None, default_start=course_start, default_end=today
    )
    rows = _absences_rows_for_range(start_d, end_d)
    teachers = list_teachers_available_for_absence(on_date=target_day)
    return request.app.state.templates.TemplateResponse(
        "ausencias/absences_new.html",
        ctx(
            request,
            user=user,
            title="Nueva ausencia",
            absences=rows,
            summary_from=summary_from_s,
            summary_to=summary_to_s,
            target_day=target_day,
            target_day_is_lectivo=is_school_day(target_day),
            teachers=teachers,
            form_error=(form_error or "").strip(),
        ),
    )


@router.get("/absences/manage", response_class=HTMLResponse)
def ausencias_absences_manage(
    request: Request,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None, alias="to"),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    today = today_madrid()
    course_start = date.fromisoformat(get_course_start_iso(today))
    start_d, end_d, start_s, end_s = _parse_absence_range(
        from_, to, default_start=course_start, default_end=today
    )
    rows = _absences_rows_for_range(start_d, end_d)
    return request.app.state.templates.TemplateResponse(
        "ausencias/absences_manage.html",
        ctx(
            request,
            user=user,
            title="Ver ausencias",
            absences=rows,
            filters={"from": start_s, "to": end_s},
            can_manage_absence_records=_can_manage_absence_records(user),
        ),
    )


@router.get("/absences/new", response_class=HTMLResponse)
def ausencias_absences_new(
    request: Request,
    d: str | None = Query(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    target = today_madrid()
    if d:
        try:
            target = date.fromisoformat(d.strip()[:10])
        except ValueError:
            pass
    return _template_absences_new(request, user, target_day=target)


@router.get("/absences/categorize", response_class=HTMLResponse)
def ausencias_absences_categorize(
    request: Request,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None, alias="to"),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    today = today_madrid()
    course_start = date.fromisoformat(get_course_start_iso(today))
    start_d, end_d, start_s, end_s = _parse_absence_range(
        from_, to, default_start=course_start, default_end=today
    )
    rows = _absences_rows_for_range(start_d, end_d, uncategorized_only=True)
    return request.app.state.templates.TemplateResponse(
        "ausencias/absences_categorize.html",
        ctx(
            request,
            user=user,
            title="Catalogar ausencias",
            absences=rows,
            filters={"from": start_s, "to": end_s},
            redirect_base="/ausencias/absences/categorize",
            catalog_options=list(ABSENCE_CATEGORIES),
        ),
    )


@router.post("/absences")
def ausencias_absences_create(
    request: Request,
    day: str = Form(...),
    teacher_id: int = Form(...),
    hours_mode: str = Form("all"),
    hour_from: int | None = Form(default=None),
    hour_to: int | None = Form(default=None),
    cause: str = Form(...),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)

    try:
        on_date = date.fromisoformat(day)
    except ValueError:
        return RedirectResponse("/ausencias/absences/new", status_code=303)

    if not is_school_day(on_date):
        return _template_absences_new(
            request,
            user,
            target_day=on_date,
            form_error="Solo se pueden registrar ausencias en días lectivos según el calendario escolar.",
        )

    cause_clean = (cause or "").strip()
    if not cause_clean:
        return _template_absences_new(
            request, user, target_day=on_date, form_error="La causa es obligatoria."
        )

    hours_mask = _hours_mask_from_form(hours_mode, hour_from, hour_to)
    if hours_mask is None:
        return _template_absences_new(
            request,
            user,
            target_day=on_date,
            form_error="Selecciona un rango válido de horas.",
        )

    absence_id = upsert_absence(
        teacher_id=teacher_id,
        on_date=on_date,
        hours_mask=hours_mask,
        note=cause_clean,
    )
    add_action_log(
        user_id=user.get("id"),
        action="absence_upsert",
        entity="absence",
        entity_id=absence_id,
        detail=f"Ausencia guardada para {on_date.isoformat()}",
    )
    return RedirectResponse(f"/ausencias/absences/new?d={on_date.isoformat()}", status_code=303)


@router.post("/absences/category")
def ausencias_absences_set_category(
    absence_id: int = Form(...),
    category: str = Form(""),
    from_: str | None = Form(default=None, alias="from"),
    to: str | None = Form(default=None),
    redirect_base: str | None = Form(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    cat_code = (category or "").strip().upper()
    if len(cat_code) != 1 or cat_code not in ALLOWED_ABSENCE_CATEGORY_CODES:
        url = _absences_redirect_url(redirect_base, from_, to)
        return RedirectResponse(url, status_code=303)
    update_absence_category(absence_id=absence_id, category=cat_code)
    add_action_log(
        user_id=user.get("id"),
        action="absence_categorize",
        entity="absence",
        entity_id=absence_id,
        detail=f"Ausencia categorizada como {cat_code}",
    )
    url = _absences_redirect_url(redirect_base, from_, to)
    return RedirectResponse(url, status_code=303)


@router.post("/absences/delete")
def ausencias_absences_delete(
    absence_id: int = Form(...),
    from_: str | None = Form(default=None, alias="from"),
    to: str | None = Form(default=None),
    redirect_base: str | None = Form(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    delete_absence(absence_id=absence_id)
    add_action_log(
        user_id=user.get("id"),
        action="absence_delete",
        entity="absence",
        entity_id=absence_id,
        detail="Ausencia eliminada",
    )
    url = _absences_redirect_url(redirect_base, from_, to)
    return RedirectResponse(url, status_code=303)


@router.get("/absences/edit/{absence_id}", response_class=HTMLResponse)
def ausencias_absences_edit_get(
    request: Request,
    absence_id: int,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None, alias="to"),
    error: str | None = Query(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    row = get_absence_by_id(absence_id=absence_id)
    if not row:
        raise HTTPException(status_code=404, detail="Ausencia no encontrada.")
    today = today_madrid()
    course_start = date.fromisoformat(get_course_start_iso(today))
    _, _, start_s, end_s = _parse_absence_range(
        from_, to, default_start=course_start, default_end=today
    )
    raw_date = row["date"]
    if hasattr(raw_date, "isoformat"):
        edit_date_iso = raw_date.isoformat()[:10]
    else:
        edit_date_iso = str(raw_date)[:10]
    mask = int(row.get("hours_mask") or 0)
    edit_mode, edit_hf, edit_ht = _mode_and_hours_from_mask(mask)
    return request.app.state.templates.TemplateResponse(
        "ausencias/absences_edit.html",
        ctx(
            request,
            user=user,
            title="Editar ausencia",
            absence=row,
            absence_id=absence_id,
            filters={"from": start_s, "to": end_s},
            edit_date_iso=edit_date_iso,
            edit_mode=edit_mode,
            edit_hour_from=edit_hf,
            edit_hour_to=edit_ht,
            edit_note=str(row.get("note") or ""),
            edit_category=str(row.get("category") or ""),
            error=(error or "").strip(),
        ),
    )


@router.post("/absences/edit")
def ausencias_absences_edit_post(
    absence_id: int = Form(...),
    day: str = Form(...),
    mode: str = Form("all"),
    hour_from: int | None = Form(default=None),
    hour_to: int | None = Form(default=None),
    note: str = Form(""),
    category: str = Form(""),
    from_: str | None = Form(default=None, alias="from"),
    to: str | None = Form(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    try:
        on_date = date.fromisoformat(day)
    except ValueError:
        return RedirectResponse(f"/ausencias/absences/edit/{absence_id}", status_code=303)
    q_from = (from_ or "").strip()
    q_to = (to or "").strip()
    edit_range_q = f"from={q_from}&to={q_to}&" if q_from and q_to else ""
    if not is_school_day(on_date):
        return RedirectResponse(
            f"/ausencias/absences/edit/{absence_id}?{edit_range_q}error=non_school_day",
            status_code=303,
        )
    hours_mask = _hours_mask_from_form(mode, hour_from, hour_to)
    if hours_mask is None:
        return RedirectResponse(
            f"/ausencias/absences/edit/{absence_id}?from={(from_ or '').strip()}&to={(to or '').strip()}",
            status_code=303,
        )
    try:
        update_absence_by_id(
            absence_id=absence_id,
            on_date=on_date,
            hours_mask=hours_mask,
            note=(note or "").strip(),
            category=(category or "").strip() or None,
        )
    except ValueError as exc:
        msg = str(exc)
        base_q = edit_range_q
        if "Ya existe" in msg:
            err = "date_conflict"
        elif "no encontrada" in msg.lower():
            return RedirectResponse(
                f"/ausencias/absences/manage?from={q_from}&to={q_to}" if q_from and q_to else "/ausencias/absences/manage",
                status_code=303,
            )
        else:
            err = "invalid"
        return RedirectResponse(f"/ausencias/absences/edit/{absence_id}?{base_q}error={err}", status_code=303)
    add_action_log(
        user_id=user.get("id"),
        action="absence_edit",
        entity="absence",
        entity_id=absence_id,
        detail=f"Ausencia {absence_id} actualizada",
    )
    url = _absences_redirect_url("/ausencias/absences/manage", from_, to)
    return RedirectResponse(url, status_code=303)


@router.get("/schedule", response_class=HTMLResponse)
def ausencias_schedule_redirect(user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    return RedirectResponse("/admin/schedules/", status_code=303)


@router.get("/schedule/export.pdf")
def ausencias_schedule_export_pdf_redirect(
    teacher_id: int = Query(...),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    return RedirectResponse(f"/admin/schedules/export.pdf?teacher_id={teacher_id}", status_code=303)


@router.get("/leaves/manage", response_class=HTMLResponse)
def ausencias_leaves_manage(request: Request, user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    rows = list_leaves(include_closed=True)
    active_items, closed_items = _build_leave_list_items(rows)
    return request.app.state.templates.TemplateResponse(
        "ausencias/leaves_manage.html",
        ctx(
            request,
            user=user,
            title="Ver bajas",
            active_items=active_items,
            closed_items=closed_items,
            can_manage_absence_records=_can_manage_absence_records(user),
            show_leave_actions=True,
        ),
    )


@router.get("/leaves/edit/{leave_id}", response_class=HTMLResponse)
def ausencias_leaves_edit_get(
    request: Request,
    leave_id: int,
    error: str | None = Query(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    row = get_leave_by_id(leave_id=leave_id)
    if not row or row.get("is_substitution"):
        raise HTTPException(status_code=404, detail="Baja no encontrada.")
    cat = str(row.get("category") or "").strip().upper()
    current_category = cat if cat in ALLOWED_ABSENCE_CATEGORY_CODES else ""
    return request.app.state.templates.TemplateResponse(
        "ausencias/leaves_edit.html",
        ctx(
            request,
            user=user,
            title="Editar baja",
            leave=row,
            leave_id=leave_id,
            edit_start_iso=_leave_date_iso(row["start_date"]) or "",
            edit_end_iso=_leave_date_iso(row["end_date"]) or "",
            edit_cause=str(row.get("cause") or ""),
            edit_leave_kind=str(row.get("leave_kind") or "baja").strip().lower(),
            current_category=current_category,
            catalog_options=list(ABSENCE_CATEGORIES),
            error=(error or "").strip(),
        ),
    )


@router.post("/leaves/edit")
def ausencias_leaves_edit_post(
    leave_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str | None = Form(default=None),
    cause: str = Form(""),
    category: str = Form(""),
    leave_kind: str = Form("baja"),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    try:
        start_d = date.fromisoformat(start_date.strip()[:10])
    except ValueError:
        return RedirectResponse(f"/ausencias/leaves/edit/{leave_id}?error=invalid_date", status_code=303)
    end_raw = (end_date or "").strip()
    end_d: date | None
    if not end_raw:
        end_d = None
    else:
        try:
            end_d = date.fromisoformat(end_raw[:10])
        except ValueError:
            return RedirectResponse(f"/ausencias/leaves/edit/{leave_id}?error=invalid_date", status_code=303)
    cat_clean = (category or "").strip().upper()
    if not cat_clean:
        cat_final = None
    elif cat_clean in ALLOWED_ABSENCE_CATEGORY_CODES:
        cat_final = cat_clean
    else:
        return RedirectResponse(f"/ausencias/leaves/edit/{leave_id}?error=invalid_category", status_code=303)
    try:
        update_leave_record(
            leave_id=leave_id,
            start_date=start_d,
            end_date=end_d,
            cause=(cause or "").strip(),
            category=cat_final,
            leave_kind=(leave_kind or "baja").strip(),
        )
    except ValueError:
        return RedirectResponse(f"/ausencias/leaves/edit/{leave_id}?error=save", status_code=303)
    add_action_log(
        user_id=user.get("id"),
        action="leave_edit",
        entity="leave",
        entity_id=leave_id,
        detail=f"Baja {leave_id} actualizada",
    )
    return RedirectResponse("/ausencias/leaves/manage", status_code=303)


@router.post("/leaves/delete")
def ausencias_leaves_delete_post(
    leave_id: int = Form(...),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    try:
        delete_leave_subtree(leave_id=leave_id)
    except ValueError:
        return RedirectResponse("/ausencias/leaves/manage", status_code=303)
    add_action_log(
        user_id=user.get("id"),
        action="leave_delete",
        entity="leave",
        entity_id=leave_id,
        detail=f"Baja {leave_id} eliminada (subárbol)",
    )
    return RedirectResponse("/ausencias/leaves/manage", status_code=303)


@router.get("/leaves/new", response_class=HTMLResponse)
def ausencias_leaves_new(request: Request, user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    rows = list_leaves(include_closed=True)
    active_items, closed_items = _build_leave_list_items(rows)
    return request.app.state.templates.TemplateResponse(
        "ausencias/leaves_new.html",
        ctx(
            request,
            user=user,
            title="Iniciar baja",
            teachers=list_active_teachers(),
            active_items=active_items,
            closed_items=closed_items,
            can_manage_absence_records=_can_manage_absence_records(user),
            show_leave_actions=False,
        ),
    )


@router.get("/leaves/categorize", response_class=HTMLResponse)
def ausencias_leaves_categorize(
    request: Request,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None, alias="to"),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    today = today_madrid()
    course_start = date.fromisoformat(get_course_start_iso(today))
    start_d, end_d, start_s, end_s = _parse_absence_range(
        from_, to, default_start=course_start, default_end=today
    )
    rows = list_leaves_uncategorized_in_range(from_date=start_d, to_date=end_d)
    return request.app.state.templates.TemplateResponse(
        "ausencias/leaves_categorize.html",
        ctx(
            request,
            user=user,
            title="Catalogar bajas",
            leaves=rows,
            filters={"from": start_s, "to": end_s},
            redirect_base="/ausencias/leaves/categorize",
            catalog_options=list(ABSENCE_CATEGORIES),
        ),
    )


def _leaves_by_id(rows: list[dict]) -> dict[int, dict]:
    return {int(r["id"]): r for r in rows}


def _substitution_chain_parts(by_id: dict[int, dict], leaf_id: int) -> list[str]:
    """Sube por ``parent_leave_id`` desde la fila sustitución hasta la raíz.

    Si dos pasos consecutivos tienen el mismo ``teacher_id`` (vínculos redundantes
    o datos incoherentes), solo se muestra un nombre para no duplicar (p. ej. ``s2 <- s1 <- p1``).
    """
    parts: list[str] = []
    cur_id: int | None = leaf_id
    seen: set[int] = set()
    prev_teacher_id: int | None = None
    while cur_id is not None and cur_id not in seen:
        seen.add(cur_id)
        row = by_id.get(cur_id)
        if not row:
            break
        tid_raw = row.get("teacher_id")
        tid = int(tid_raw) if tid_raw is not None else None
        pid = row.get("parent_leave_id")
        next_id = int(pid) if pid is not None else None
        if tid is not None and tid == prev_teacher_id:
            cur_id = next_id
            continue
        parts.append(str(row.get("teacher_name") or "").strip() or "?")
        prev_teacher_id = tid
        cur_id = next_id
    return parts


def _substitution_chain_label(by_id: dict[int, dict], leaf_id: int) -> str:
    """Cadena desde el sustituto de esta fila hasta el titular (ej. s2 <- s1 <- Pérez)."""
    return " <- ".join(_substitution_chain_parts(by_id, leaf_id))


@router.get("/leaves/substitutions", response_class=HTMLResponse)
def ausencias_leaves_substitutions_page(request: Request, user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    rows = list_leaves(include_closed=True)
    by_id = _leaves_by_id(rows)
    subs = [r for r in rows if r.get("is_substitution")]
    items: list[dict] = []
    for s in subs:
        lid = int(s["id"])
        parts = _substitution_chain_parts(by_id, lid)
        chain = " <- ".join(parts)
        depth = len(parts)
        sd = s["start_date"]
        ed = s["end_date"]
        items.append(
            {
                "id": lid,
                "chain_label": chain,
                "depth": depth,
                "start_iso": _leave_date_iso(sd) or "",
                "end_iso": _leave_date_iso(ed) if ed is not None else None,
                "start_sort": _date_ord(sd),
                "end_sort": _date_ord(ed) if ed is not None else 0,
            }
        )
    items.sort(key=lambda x: (-x["depth"], -x["start_sort"], x["id"]))
    active_substitutions = [x for x in items if x["end_iso"] is None]
    closed_substitutions = [x for x in items if x["end_iso"] is not None]
    closed_substitutions.sort(key=lambda x: (-x["end_sort"], -x["depth"], -x["start_sort"], x["id"]))
    return request.app.state.templates.TemplateResponse(
        "ausencias/leaves_substitutions.html",
        ctx(
            request,
            user=user,
            title="Sustituciones",
            active_substitutions=active_substitutions,
            closed_substitutions=closed_substitutions,
            can_manage_absence_records=_can_manage_absence_records(user),
        ),
    )


@router.get("/leaves/substitution-edit/{leave_id}", response_class=HTMLResponse)
def ausencias_leaves_substitution_edit_get(
    request: Request,
    leave_id: int,
    error: str | None = Query(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    row = get_leave_by_id(leave_id=leave_id)
    if not row or not row.get("is_substitution"):
        raise HTTPException(status_code=404, detail="Sustitución no encontrada.")
    rows = list_leaves(include_closed=True)
    by_id = _leaves_by_id(rows)
    chain = _substitution_chain_label(by_id, leave_id)
    return request.app.state.templates.TemplateResponse(
        "ausencias/leaves_substitution_edit.html",
        ctx(
            request,
            user=user,
            title="Editar fechas de sustitución",
            leave_id=leave_id,
            chain_label=chain,
            edit_start_iso=_leave_date_iso(row["start_date"]) or "",
            edit_end_iso=_leave_date_iso(row["end_date"]) if row.get("end_date") is not None else "",
            error=(error or "").strip(),
        ),
    )


@router.post("/leaves/substitution-edit")
def ausencias_leaves_substitution_edit_post(
    leave_id: int = Form(...),
    start_date: str = Form(...),
    end_date: str | None = Form(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    dest = "/ausencias/leaves/substitutions"
    try:
        start_d = date.fromisoformat((start_date or "").strip()[:10])
    except ValueError:
        return RedirectResponse(f"/ausencias/leaves/substitution-edit/{leave_id}?error=invalid_date", status_code=303)
    end_raw = (end_date or "").strip()
    end_d: date | None
    if not end_raw:
        end_d = None
    else:
        try:
            end_d = date.fromisoformat(end_raw[:10])
        except ValueError:
            return RedirectResponse(f"/ausencias/leaves/substitution-edit/{leave_id}?error=invalid_date", status_code=303)
    try:
        update_substitution_leave_dates(leave_id=leave_id, start_date=start_d, end_date=end_d)
    except ValueError:
        return RedirectResponse(f"/ausencias/leaves/substitution-edit/{leave_id}?error=save", status_code=303)
    add_action_log(
        user_id=user.get("id"),
        action="substitution_dates_edit",
        entity="leave",
        entity_id=leave_id,
        detail=f"Sustitución {leave_id}: fechas {start_d.isoformat()} – {(end_d.isoformat() if end_d else 'abierta')}",
    )
    return RedirectResponse(dest, status_code=303)


@router.get("/leaves/finish", response_class=HTMLResponse)
def ausencias_leaves_finish_page(request: Request, user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    rows = list_leaves(include_closed=False)
    open_non_sub = [r for r in rows if not r.get("is_substitution") and r.get("end_date") is None]
    items = []
    for r in open_non_sub:
        sd = r["start_date"]
        items.append(
            {
                "leave_id": int(r["id"]),
                "teacher_name": str(r.get("teacher_name") or ""),
                "start_date": _leave_date_iso(sd) or "",
            }
        )
    items.sort(key=lambda x: (x["start_date"], x["leave_id"]))
    return request.app.state.templates.TemplateResponse(
        "ausencias/leaves_finish.html",
        ctx(
            request,
            user=user,
            title="Finalizar baja",
            open_items=items,
            can_catalog_leaves=_can_manage_absence_records(user),
        ),
    )


@router.get("/substitutions", response_class=HTMLResponse)
def ausencias_substitutions_hub(request: Request, user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    return request.app.state.templates.TemplateResponse(
        "ausencias/substitutions_hub.html",
        ctx(
            request,
            user=user,
            title="Sustituciones",
            can_catalog_leaves=_can_manage_absence_records(user),
        ),
    )


@router.get("/substitutions/start", response_class=HTMLResponse)
def ausencias_substitutions_start(request: Request, user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    parents = list_open_parent_leaves_without_active_substitution()
    exprofes = list_exprofes_for_substitution()
    default_substitution_mode = "nuevo" if not exprofes else "exprofe"
    return request.app.state.templates.TemplateResponse(
        "ausencias/substitutions_start.html",
        ctx(
            request,
            user=user,
            title="Iniciar sustitución",
            parent_leaves=parents,
            exprofes=exprofes,
            default_substitution_mode=default_substitution_mode,
            can_catalog_leaves=_can_manage_absence_records(user),
        ),
    )


@router.get("/substitutions/finish", response_class=HTMLResponse)
def ausencias_substitutions_finish_page(request: Request, user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    resign_candidates = list_teachers_eligible_substitution_resign_finish()
    return request.app.state.templates.TemplateResponse(
        "ausencias/substitutions_finish.html",
        ctx(
            request,
            user=user,
            title="Finalizar sustitución",
            resign_candidates=resign_candidates,
            can_catalog_leaves=_can_manage_absence_records(user),
        ),
    )


@router.get("/leaves", response_class=HTMLResponse)
def ausencias_leaves_hub(request: Request, user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    return request.app.state.templates.TemplateResponse(
        "ausencias/leaves_hub.html",
        ctx(
            request,
            user=user,
            title="Bajas",
            can_catalog_leaves=_can_manage_absence_records(user),
        ),
    )


@router.post("/leaves")
def ausencias_leaves_create(
    teacher_id: int = Form(...),
    start_date: str = Form(...),
    cause: str = Form(...),
    leave_kind: str = Form(...),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    kind = (leave_kind or "").strip().lower()
    if kind not in {"baja", "excedencia"}:
        return RedirectResponse("/ausencias/leaves/new", status_code=303)
    cause_clean = (cause or "").strip()
    if not cause_clean:
        return RedirectResponse("/ausencias/leaves/new", status_code=303)
    try:
        start = date.fromisoformat(start_date.strip()[:10])
    except ValueError:
        return RedirectResponse("/ausencias/leaves/new", status_code=303)

    try:
        leave_id = create_leave_root(
            teacher_id=teacher_id,
            start_date=start,
            cause=cause_clean,
            category=None,
            leave_kind=kind,
        )
    except ValueError:
        return RedirectResponse("/ausencias/leaves/new", status_code=303)

    add_action_log(
        user_id=user.get("id"),
        action="leave_create",
        entity="leave",
        entity_id=leave_id,
        detail=f"Baja creada con fecha {start.isoformat()}",
    )
    return RedirectResponse("/ausencias/leaves/new", status_code=303)


@router.post("/leaves/close")
def ausencias_leaves_close(
    leave_id: int = Form(...),
    end_date: str = Form(...),
    mode: str = Form("cascade"),
    next_: str | None = Form(default=None, alias="next"),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    dest = _leave_close_redirect(next_)
    try:
        end_d = date.fromisoformat(end_date)
        close_leave(leave_id=leave_id, end_date=end_d, mode=mode)
    except ValueError:
        return RedirectResponse(dest, status_code=303)

    add_action_log(
        user_id=user.get("id"),
        action="leave_close",
        entity="leave",
        entity_id=leave_id,
        detail=f"Baja cerrada en {end_d.isoformat()} ({mode})",
    )
    return RedirectResponse(dest, status_code=303)


@router.post("/leaves/finalize-baja")
def ausencias_leaves_finalize_baja(
    leave_id: int = Form(...),
    end_date: str = Form(...),
    next_: str | None = Form(default=None, alias="next"),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    dest = _leave_close_redirect(next_)
    try:
        end_d = date.fromisoformat(end_date.strip()[:10])
    except ValueError:
        return RedirectResponse(dest, status_code=303)

    leave_row = get_leave_by_id(leave_id=leave_id)
    tip_sub_id = get_open_substitution_tip_teacher_id(leave_id=leave_id)

    try:
        finalize_baja_leave(leave_id=leave_id, end_date=end_d)
    except ValueError:
        return RedirectResponse(dest, status_code=303)

    add_action_log(
        user_id=user.get("id"),
        action="leave_finalize_baja",
        entity="leave",
        entity_id=leave_id,
        detail=f"Finalizar baja hasta {end_d.isoformat()} (cadena y sync)",
    )

    try:
        from db.portal_published_notices import create_reincorporacion_notice

        if leave_row and leave_row.get("teacher_id"):
            reincorp = get_user_by_id(int(leave_row["teacher_id"]))
            if reincorp:
                alias = (
                    (reincorp.get("alias") or "").strip()
                    or (reincorp.get("name") or "").strip()
                )
                departamento = (reincorp.get("departamento") or "").strip()
                sustituto_nombre = ""
                if tip_sub_id is not None:
                    tip_user = get_user_by_id(int(tip_sub_id))
                    if tip_user:
                        sustituto_nombre = (tip_user.get("name") or "").strip()
                create_reincorporacion_notice(
                    created_by=user.get("id"),
                    fecha=end_d,
                    profesor_alias=alias,
                    departamento=departamento,
                    sustituto_nombre=sustituto_nombre,
                )
    except Exception:
        pass

    return RedirectResponse(dest, status_code=303)


@router.post("/substitutions/finalize-resign")
def ausencias_substitutions_finalize_resign(
    substitute_teacher_id: int = Form(...),
    end_date: str = Form(...),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    dest = "/ausencias/substitutions/finish"
    try:
        end_d = date.fromisoformat(end_date.strip()[:10])
        lid = finalize_substitution_resignation(
            substitute_teacher_id=substitute_teacher_id,
            end_date=end_d,
        )
    except ValueError:
        return RedirectResponse(dest, status_code=303)

    add_action_log(
        user_id=user.get("id"),
        action="substitution_resign_finish",
        entity="leave",
        entity_id=lid,
        detail=f"Renuncia sustitución profesor_id={substitute_teacher_id} hasta {end_d.isoformat()}",
    )
    return RedirectResponse(dest, status_code=303)


@router.post("/leaves/category")
def ausencias_leaves_set_category(
    leave_id: int = Form(...),
    category: str = Form(""),
    from_: str | None = Form(default=None, alias="from"),
    to: str | None = Form(default=None),
    redirect_base: str | None = Form(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    _require_manage_absence_records(user)
    cat_code = (category or "").strip().upper()
    url = _leaves_categorize_redirect_url(from_, to, redirect_base)
    if len(cat_code) != 1 or cat_code not in ALLOWED_ABSENCE_CATEGORY_CODES:
        return RedirectResponse(url, status_code=303)
    update_leave_category(leave_id=leave_id, category=cat_code)
    add_action_log(
        user_id=user.get("id"),
        action="leave_categorize",
        entity="leave",
        entity_id=leave_id,
        detail=f"Baja categorizada como {cat_code}",
    )
    return RedirectResponse(url, status_code=303)


@router.post("/leaves/substitute")
async def ausencias_leaves_substitute(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    """multipart: en modo «nuevo» no se envía ``substitute_teacher_id`` (select desactivado)."""
    _require_ausencias_app(user)
    form = await request.form()

    def _field(name: str) -> str | None:
        raw = form.get(name)
        if raw is None:
            return None
        s = str(raw).strip()
        return s if s else None

    dest = _substitute_redirect(_field("next"))
    mode = (_field("substitution_mode") or "").lower()
    if mode not in {"exprofe", "nuevo"}:
        return RedirectResponse(dest, status_code=303)

    leave_raw = form.get("leave_id")
    if leave_raw is None:
        return RedirectResponse(dest, status_code=303)
    try:
        leave_id = int(str(leave_raw).strip())
    except ValueError:
        return RedirectResponse(dest, status_code=303)

    start_s = _field("start_date")
    if not start_s:
        return RedirectResponse(dest, status_code=303)
    try:
        start_d = date.fromisoformat(start_s[:10])
    except ValueError:
        return RedirectResponse(dest, status_code=303)

    substitute_teacher_id = _field("substitute_teacher_id")
    new_name = _field("new_name")
    new_email = _field("new_email")
    new_role = _field("new_role")
    new_alias = _field("new_alias")

    substitute_id: int | None = None
    created_new_user = False

    if mode == "exprofe":
        raw = (substitute_teacher_id or "").strip()
        if not raw:
            return RedirectResponse(dest, status_code=303)
        try:
            substitute_id = int(raw)
        except ValueError:
            return RedirectResponse(dest, status_code=303)
    else:
        lv_row = get_leave_by_id(leave_id=leave_id)
        if (
            not lv_row
            or lv_row.get("is_substitution")
            or lv_row.get("end_date") is not None
        ):
            return RedirectResponse(dest, status_code=303)
        substituted = get_user_by_id(int(lv_row["teacher_id"]))
        if not substituted:
            return RedirectResponse(dest, status_code=303)
        tutor_inherited = (substituted.get("tutor") or "").strip() or None
        dept_inherited = (substituted.get("departamento") or "").strip() or None

        nm = (new_name or "").strip()
        em = (new_email or "").strip().lower()
        rl = (new_role or "").strip()
        if not nm or not em or rl not in ROLES_TODOS:
            return RedirectResponse(dest, status_code=303)
        try:
            substitute_id = create_user_admin_returning_id(
                name=nm,
                email=em,
                role=rl,
                created_by=user.get("id"),
                alias=(new_alias or "").strip() or None,
                status="activo",
                titular=False,
                tutor=tutor_inherited,
                departamento=dept_inherited,
                active=1,
            )
            created_new_user = True
        except ValueError:
            return RedirectResponse(dest, status_code=303)
        except UniqueViolation:
            return RedirectResponse(dest, status_code=303)

    if substitute_id is None:
        return RedirectResponse(dest, status_code=303)

    try:
        sub_id = create_substitution(
            leave_id=leave_id,
            substitute_teacher_id=substitute_id,
            start_date=start_d,
        )
    except ValueError:
        return RedirectResponse(dest, status_code=303)

    detail = f"Sustitución creada desde {start_d.isoformat()} para leave_id={leave_id}"
    if created_new_user:
        detail += f"; nuevo usuario id={substitute_id}"
    add_action_log(
        user_id=user.get("id"),
        action="substitution_create",
        entity="leave",
        entity_id=sub_id,
        detail=detail,
    )

    try:
        from db.portal_published_notices import create_sustitucion_notice

        leave_row = get_leave_by_id(leave_id=leave_id) or {}
        substituted_user = get_user_by_id(int(leave_row["teacher_id"])) if leave_row.get("teacher_id") else None
        substitute_user = get_user_by_id(int(substitute_id))
        if substituted_user and substitute_user:
            sustituido_alias = (
                (substituted_user.get("alias") or "").strip()
                or (substituted_user.get("name") or "").strip()
            )
            sustituto_nombre = (substitute_user.get("name") or "").strip()
            departamento = (
                (substitute_user.get("departamento") or "").strip()
                or (substituted_user.get("departamento") or "").strip()
            )
            create_sustitucion_notice(
                created_by=user.get("id"),
                fecha=start_d,
                sustituto_nombre=sustituto_nombre,
                departamento=departamento,
                sustituido_alias=sustituido_alias,
            )
    except Exception:
        pass

    return RedirectResponse(dest, status_code=303)


@router.get("/leaves/substitute-options")
def ausencias_substitute_options(
    leave_id: int = Query(...),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    teachers = list_available_substitute_teachers(for_leave_id=leave_id)
    options = "".join([f'<option value="{t["id"]}">{t["name"]}</option>' for t in teachers])
    return HTMLResponse(options)


@router.get("/actions")
def ausencias_actions_legacy_redirect(user: dict = Depends(load_user_dep)):
    """El listado vive en Backup → Registro; se mantiene la URL por marcadores."""
    if not has_permission(user, PERM_BACKUP):
        raise HTTPException(
            status_code=403,
            detail="El registro de acciones está en Administración → Backup → Registro → Ausencias.",
        )
    return RedirectResponse("/admin/backup/registro/ausencias-actions", status_code=303)


@router.get("/absences/export.xlsx")
def ausencias_absences_export_xlsx(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None, alias="to"),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)

    today = today_madrid()
    default_from = (today - timedelta(days=30)).isoformat()
    start_s = (from_ or default_from).strip()
    end_s = (to or today.isoformat()).strip()
    try:
        start_d = date.fromisoformat(start_s)
        end_d = date.fromisoformat(end_s)
    except ValueError:
        start_d = date.fromisoformat(default_from)
        end_d = today
    if start_d > end_d:
        start_d, end_d = end_d, start_d

    rows = list_absences_range(from_date=start_d, to_date=end_d)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ausencias"
    ws.append(["Fecha", "Profesor", "Horas", "Categoría", "Observaciones"])
    for a in rows:
        ws.append(
            [
                str(a.get("date") or ""),
                a.get("teacher_name") or "",
                _mask_to_human(int(a.get("hours_mask") or 0)),
                a.get("category") or "",
                a.get("note") or "",
            ]
        )
    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return Response(
        stream.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=ausencias_{start_d.isoformat()}_{end_d.isoformat()}.xlsx"
        },
    )


@router.get("/reports/daily", response_class=HTMLResponse)
def ausencias_report_daily_form(
    request: Request,
    day: str | None = Query(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    target = (day or today_madrid().isoformat()).strip()
    return request.app.state.templates.TemplateResponse(
        "ausencias/reports_daily.html",
        ctx(
            request,
            user=user,
            title="Parte diario de ausencias",
            day=target,
            observaciones_prefill="",
        ),
    )


@router.get("/reports/daily/view", response_class=HTMLResponse)
def ausencias_report_daily_view(
    request: Request,
    day: str = Query(...),
    obs: str | None = Query(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    try:
        target = date.fromisoformat(day)
    except ValueError:
        target = today_madrid()
    obs_clean = (obs or "").strip()
    preview = build_daily_report_preview(target, obs_clean)
    return request.app.state.templates.TemplateResponse(
        "ausencias/reports_daily.html",
        ctx(
            request,
            user=user,
            title="Parte diario de ausencias",
            day=target.isoformat(),
            observaciones_prefill=obs_clean,
            preview=preview,
        ),
    )


@router.post("/reports/daily/pdf")
def ausencias_report_daily_pdf(
    day: str = Form(...),
    obs: str = Form(""),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    try:
        target = date.fromisoformat(day)
    except ValueError:
        return RedirectResponse("/ausencias/reports/daily", status_code=303)

    preview = build_daily_report_preview(target, (obs or "").strip())

    pdf_bytes = render_daily_report_pdf_bytes(preview)
    filename = safe_pdf_filename(f"parte_diario_{target.isoformat()}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/monthly", response_class=HTMLResponse)
def ausencias_report_monthly_form(
    request: Request,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    blocked_pdf: str | None = Query(default=None),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    today = today_madrid()
    first = date(today.year, today.month, 1)
    return request.app.state.templates.TemplateResponse(
        "ausencias/reports_monthly.html",
        ctx(
            request,
            user=user,
            title="Parte mensual",
            date_from=(date_from or first.isoformat()),
            date_to=(date_to or today.isoformat()),
            blocked_pdf=bool((blocked_pdf or "").strip() == "1"),
            rows_catalogadas=[],
            rows_sin_catalogar=[],
            has_uncategorized=False,
            monthly_preview=False,
            can_catalog_absences=_can_manage_absence_records(user),
        ),
    )


@router.get("/reports/monthly/view", response_class=HTMLResponse)
def ausencias_report_monthly_view(
    request: Request,
    date_from: str = Query(...),
    date_to: str = Query(...),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    try:
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
    except ValueError:
        return RedirectResponse("/ausencias/reports/monthly", status_code=303)
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    report = build_monthly_report(date_from=d_from, date_to=d_to)

    return request.app.state.templates.TemplateResponse(
        "ausencias/reports_monthly.html",
        ctx(
            request,
            user=user,
            title="Parte mensual",
            date_from=d_from.isoformat(),
            date_to=d_to.isoformat(),
            rows_catalogadas=report["rows_catalogadas"],
            rows_sin_catalogar=report["rows_sin_catalogar"],
            has_uncategorized=report["has_uncategorized"],
            blocked_pdf=False,
            monthly_preview=True,
            can_catalog_absences=_can_manage_absence_records(user),
        ),
    )


@router.get("/reports/monthly/pdf")
def ausencias_report_monthly_pdf(
    date_from: str = Query(...),
    date_to: str = Query(...),
    user: dict = Depends(load_user_dep),
):
    _require_ausencias_app(user)
    try:
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
    except ValueError:
        return RedirectResponse("/ausencias/reports/monthly", status_code=303)
    if d_from > d_to:
        d_from, d_to = d_to, d_from

    report = build_monthly_report(date_from=d_from, date_to=d_to)
    if report["has_uncategorized"]:
        return RedirectResponse(
            f"/ausencias/reports/monthly?date_from={d_from.isoformat()}&date_to={d_to.isoformat()}&blocked_pdf=1",
            status_code=303,
        )

    pdf_bytes = render_monthly_report_pdf_bytes(
        date_from=d_from,
        date_to=d_to,
        pdf_body_rows=report["pdf_body_rows"],
    )
    filename = safe_pdf_filename(
        f"parte_mensual_{d_from.isoformat()}_{d_to.isoformat()}"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/imports", response_class=HTMLResponse)
def ausencias_imports_redirect(user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    return RedirectResponse("/admin/schedules/imports", status_code=303)


@router.post("/imports/teachers")
def ausencias_import_teachers_redirect(user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    return RedirectResponse("/admin/schedules/imports", status_code=303)


@router.post("/imports/schedule")
def ausencias_import_schedule_redirect(user: dict = Depends(load_user_dep)):
    _require_ausencias_app(user)
    return RedirectResponse("/admin/schedules/imports", status_code=303)

