"""Rutas HTTP bajo ``/aula-informatica``."""

from __future__ import annotations

import json
from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth import load_user_dep
from context import ctx
from aula_informatica.aulas_data import (
    AULAS_INFORMATICA,
    CLASS_HOUR_LABELS,
    NUM_PUESTOS,
    VALID_CLASS_HOURS,
    get_aula,
    get_reservation_room,
)
from aula_informatica.group_columns import grupos_por_columnas
from aula_informatica.normas_data import NORMAS_AULA_INFORMATICA_SECTIONS
from aula_informatica.queries import list_students_for_groups
from aula_informatica.session_data import (
    ESTADO_CHOICES,
    SESSION_DRAFT_KEY,
    SESSION_OK_KEY,
    SESSION_SENT_KEY,
    build_draft,
    form_state_from_rows,
    grupos_from_student_ids,
    parse_puestos_from_form,
    validate_puestos_rows,
    validate_puestos_rows_edit,
)
from aula_informatica.students_display import list_alumnos_para_puestos, parse_student_ids
from db.aula_informatica_reports import (
    get_report_for_user,
    insert_report,
    list_all_reports,
    list_puesto_incidencias_for_reports,
    list_puesto_history,
    list_reports_for_user,
    update_report,
)
from db.groups import group_exists
from db.action_logs import log_aula_informatica_action
from db.aula_informatica_access import (
    accept_aula_informatica_normas,
    has_accepted_aula_informatica_normas,
)
from reservas.db import user_has_reservation_for_slot
from utils.enums import (
    PERM_AULA_INFORMATICA_APP,
    PERM_AULA_INFORMATICA_REGISTROS,
    PERM_AULA_INFORMATICA_RASTREAR,
)
from utils.permissions import has_permission
from utils.time_madrid import today_madrid

router = APIRouter(prefix="/aula-informatica", tags=["aula-informatica"])


def _require_access(user: dict) -> None:
    if not has_permission(user, PERM_AULA_INFORMATICA_APP):
        raise HTTPException(status_code=403, detail="Sin permiso para Aula de Informática")


def _require_registros_access(user: dict) -> None:
    _require_access(user)
    if not has_permission(user, PERM_AULA_INFORMATICA_REGISTROS):
        raise HTTPException(status_code=403, detail="Sin permiso para ver registros")


def _require_rastrear_access(user: dict) -> None:
    _require_access(user)
    if not has_permission(user, PERM_AULA_INFORMATICA_RASTREAR):
        raise HTTPException(status_code=403, detail="Sin permiso para rastrear")


def _parse_session_date(raw: str) -> date | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _format_session_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def _fecha_hora_query(fecha: date, hora: str) -> str:
    return f"fecha={quote(fecha.isoformat(), safe='')}&hora={quote(hora, safe='')}"


def _parse_session_context(
    *,
    session_date: str,
    class_hour: str,
) -> tuple[date | None, str, str | None]:
    parsed_date = _parse_session_date(session_date)
    hora = (class_hour or "").strip()
    if not parsed_date:
        return None, hora, "Indica una fecha válida."
    if hora not in VALID_CLASS_HOURS:
        return parsed_date, hora, "Selecciona una hora lectiva válida."
    return parsed_date, hora, None


def _student_ids_query(student_ids: list[int]) -> str:
    return "&".join(f"student_ids={int(sid)}" for sid in student_ids)


def _report_form_state_from_puestos(puestos: list[dict]) -> dict:
    by_puesto: dict[int, dict] = {}
    for row in puestos:
        by_puesto[int(row["puesto"])] = {
            "student_id": int(row["student_id"]),
            "estado": str(row.get("estado") or "buen_estado"),
            "incidencia": str(row.get("incidencia") or ""),
        }
    return {"puestos": by_puesto}


def _mis_registro_editar_ctx(
    request: Request,
    *,
    user: dict,
    report: dict,
    aula: dict[str, str],
    parsed_date: date,
    form_error: str | None = None,
    form_state: dict | None = None,
    otras_incidencias: str | None = None,
) -> dict:
    student_ids = list(report.get("student_ids") or [])
    alumnos = list_alumnos_para_puestos(student_ids)
    if form_state is None:
        form_state = _report_form_state_from_puestos(report.get("puestos") or [])
    if otras_incidencias is None:
        otras_incidencias = str(report.get("otras_incidencias") or "")
    return ctx(
        request,
        user=user,
        title=f"Editar registro · {aula['label']}",
        nav_section="mis_registros",
        aula=aula,
        report_id=int(report["id"]),
        session_date=parsed_date.isoformat(),
        session_date_display=_format_session_date(parsed_date),
        class_hour=str(report.get("class_hour") or ""),
        grupos_display=", ".join(report.get("grupos") or []) or "—",
        student_ids=student_ids,
        alumnos=alumnos,
        alumnos_alpine_json=json.dumps(
            [{"id": int(a["id"]), "label": str(a["label"])} for a in alumnos]
        ),
        selected_initial_json=json.dumps(_puestos_selected_initial(form_state)),
        estados_initial_json=json.dumps(_puestos_estados_initial(form_state)),
        num_puestos=NUM_PUESTOS,
        estado_choices=ESTADO_CHOICES,
        form_error=form_error,
        form_state=form_state,
        otras_incidencias=otras_incidencias,
    )


def _puestos_selected_initial(form_state: dict | None) -> list[str]:
    selected = [""] * NUM_PUESTOS
    if form_state:
        for puesto, row in (form_state.get("puestos") or {}).items():
            try:
                idx = int(puesto) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= idx < NUM_PUESTOS:
                selected[idx] = str(row.get("student_id") or "")
    return selected


def _puestos_estados_initial(form_state: dict | None) -> list[str]:
    estados = ["buen_estado"] * NUM_PUESTOS
    if form_state:
        for puesto, row in (form_state.get("puestos") or {}).items():
            try:
                idx = int(puesto) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= idx < NUM_PUESTOS:
                estado = str(row.get("estado") or "buen_estado").strip()
                if estado in {"buen_estado", "incidencias"}:
                    estados[idx] = estado
    return estados


def _puestos_page_ctx(
    request: Request,
    *,
    user: dict,
    aula: dict[str, str],
    parsed_date: date,
    hora: str,
    student_ids: list[int],
    form_error: str | None = None,
    form_state: dict | None = None,
) -> dict:
    alumnos = list_alumnos_para_puestos(student_ids)
    return ctx(
        request,
        user=user,
        title=f"Asignar puestos · {aula['label']}",
        nav_section="en_el_aula",
        aula=aula,
        session_date=parsed_date.isoformat(),
        session_date_display=_format_session_date(parsed_date),
        class_hour=hora,
        student_ids=student_ids,
        alumnos=alumnos,
        alumnos_alpine_json=json.dumps(
            [{"id": int(a["id"]), "label": str(a["label"])} for a in alumnos]
        ),
        selected_initial_json=json.dumps(_puestos_selected_initial(form_state)),
        estados_initial_json=json.dumps(_puestos_estados_initial(form_state)),
        num_puestos=NUM_PUESTOS,
        estado_choices=ESTADO_CHOICES,
        form_error=form_error,
        form_state=form_state,
    )


@router.get("/", include_in_schema=False)
def aula_informatica_root(user: dict = Depends(load_user_dep)):
    _require_access(user)
    return RedirectResponse("/aula-informatica/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
def aula_informatica_dashboard(request: Request, user: dict = Depends(load_user_dep)):
    _require_access(user)
    ok_msg = request.session.pop(SESSION_OK_KEY, None)
    return request.app.state.templates.TemplateResponse(
        "aula_informatica/dashboard.html",
        ctx(
            request,
            user=user,
            title="Aula de Informática",
            nav_section="inicio",
            ok_msg=ok_msg,
        ),
    )


@router.get("/normas", response_class=HTMLResponse)
def aula_informatica_normas(request: Request, user: dict = Depends(load_user_dep)):
    _require_access(user)
    uid = user.get("id")
    if uid is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    accepted = has_accepted_aula_informatica_normas(user_id=int(uid))
    return request.app.state.templates.TemplateResponse(
        "aula_informatica/normas.html",
        ctx(
            request,
            user=user,
            title="Normas · Aula de Informática",
            nav_section="normas",
            normas_sections=NORMAS_AULA_INFORMATICA_SECTIONS,
            normas_accepted=accepted,
            normas_pending=not accepted,
        ),
    )


@router.post("/normas/aceptar")
def aula_informatica_normas_aceptar(user: dict = Depends(load_user_dep)):
    _require_access(user)
    uid = user.get("id")
    if uid is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    accept_aula_informatica_normas(user_id=int(uid))
    return RedirectResponse("/aula-informatica/dashboard", status_code=303)


@router.get("/en-el-aula", response_class=HTMLResponse)
def aula_informatica_en_el_aula(request: Request, user: dict = Depends(load_user_dep)):
    _require_access(user)
    return request.app.state.templates.TemplateResponse(
        "aula_informatica/indicar_aula.html",
        ctx(
            request,
            user=user,
            title="Indicar Aula · Aula de Informática",
            nav_section="en_el_aula",
            aulas=AULAS_INFORMATICA,
        ),
    )


@router.get("/en-el-aula/{aula_id}", response_class=HTMLResponse)
def aula_informatica_seleccionar_fecha_hora(
    request: Request,
    aula_id: str,
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    aula = get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    fecha_q = request.query_params.get("fecha")
    hora_q = (request.query_params.get("hora") or "").strip()
    parsed = _parse_session_date(fecha_q or "")
    default_date = parsed.isoformat() if parsed else today_madrid().isoformat()
    default_hour = hora_q if hora_q in VALID_CLASS_HOURS else ""

    return request.app.state.templates.TemplateResponse(
        "aula_informatica/seleccionar_fecha_hora.html",
        ctx(
            request,
            user=user,
            title=f"Seleccionar Fecha y Hora · {aula['label']}",
            nav_section="en_el_aula",
            aula=aula,
            class_hours=CLASS_HOUR_LABELS,
            default_date=default_date,
            default_hour=default_hour,
            form_error=None,
        ),
    )


@router.post("/en-el-aula/{aula_id}")
def aula_informatica_seleccionar_fecha_hora_post(
    request: Request,
    aula_id: str,
    session_date: str = Form(...),
    class_hour: str = Form(...),
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    aula = get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    parsed_date = _parse_session_date(session_date)
    hora = (class_hour or "").strip()
    form_error: str | None = None
    if not parsed_date:
        form_error = "Indica una fecha válida."
    elif hora not in VALID_CLASS_HOURS:
        form_error = "Selecciona una hora lectiva válida."

    if form_error:
        return request.app.state.templates.TemplateResponse(
            "aula_informatica/seleccionar_fecha_hora.html",
            ctx(
                request,
                user=user,
                title=f"Seleccionar Fecha y Hora · {aula['label']}",
                nav_section="en_el_aula",
                aula=aula,
                class_hours=CLASS_HOUR_LABELS,
                default_date=(parsed_date or today_madrid()).isoformat(),
                default_hour=hora if hora in VALID_CLASS_HOURS else "",
                form_error=form_error,
            ),
        )

    q = _fecha_hora_query(parsed_date, hora)
    return RedirectResponse(
        f"/aula-informatica/en-el-aula/{aula_id}/sesion?{q}",
        status_code=303,
    )


@router.get("/en-el-aula/{aula_id}/sesion/alumnos")
def aula_informatica_sesion_alumnos_json(
    aula_id: str,
    user: dict = Depends(load_user_dep),
    grupos: list[str] = Query(default=[]),
):
    _require_access(user)
    if not get_aula(aula_id):
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    clean_groups = [g.strip() for g in grupos if g and str(g).strip()]
    valid_groups = [g for g in clean_groups if group_exists(g)]
    return JSONResponse(list_students_for_groups(valid_groups))


@router.get("/en-el-aula/{aula_id}/sesion", response_class=HTMLResponse)
def aula_informatica_indicar_grupos_alumnos(
    request: Request,
    aula_id: str,
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    aula = get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    parsed_date = _parse_session_date(request.query_params.get("fecha") or "")
    hora = (request.query_params.get("hora") or "").strip()
    if not parsed_date or hora not in VALID_CLASS_HOURS:
        return RedirectResponse(f"/aula-informatica/en-el-aula/{aula_id}", status_code=303)

    grupo_columnas = grupos_por_columnas()
    return request.app.state.templates.TemplateResponse(
        "aula_informatica/indicar_grupos_alumnos.html",
        ctx(
            request,
            user=user,
            title=f"Indicar grupos y alumnos · {aula['label']}",
            nav_section="en_el_aula",
            aula=aula,
            session_date=parsed_date.isoformat(),
            session_date_display=_format_session_date(parsed_date),
            class_hour=hora,
            grupo_columnas=grupo_columnas,
            hay_grupos=any(col["grupos"] for col in grupo_columnas),
            form_error=None,
        ),
    )


@router.post("/en-el-aula/{aula_id}/sesion")
def aula_informatica_indicar_grupos_alumnos_post(
    request: Request,
    aula_id: str,
    session_date: str = Form(...),
    class_hour: str = Form(...),
    student_ids: list[int] = Form(default=[]),
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    aula = get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    parsed_date, hora, session_error = _parse_session_context(
        session_date=session_date,
        class_hour=class_hour,
    )
    if session_error or not parsed_date:
        return RedirectResponse(f"/aula-informatica/en-el-aula/{aula_id}", status_code=303)

    grupo_columnas = grupos_por_columnas()

    valid_ids = parse_student_ids([str(raw) for raw in student_ids])

    if not valid_ids:
        return request.app.state.templates.TemplateResponse(
            "aula_informatica/indicar_grupos_alumnos.html",
            ctx(
                request,
                user=user,
                title=f"Indicar grupos y alumnos · {aula['label']}",
                nav_section="en_el_aula",
                aula=aula,
                session_date=parsed_date.isoformat(),
                session_date_display=_format_session_date(parsed_date),
                class_hour=hora,
                grupo_columnas=grupo_columnas,
                hay_grupos=any(col["grupos"] for col in grupo_columnas),
                form_error="Seleccione al menos un alumno.",
            ),
        )

    q = _fecha_hora_query(parsed_date, hora)
    if valid_ids:
        q = f"{q}&{_student_ids_query(valid_ids)}"
    return RedirectResponse(
        f"/aula-informatica/en-el-aula/{aula_id}/sesion/puestos?{q}",
        status_code=303,
    )


@router.get("/en-el-aula/{aula_id}/sesion/puestos", response_class=HTMLResponse)
def aula_informatica_sesion_puestos(
    request: Request,
    aula_id: str,
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    aula = get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    parsed_date = _parse_session_date(request.query_params.get("fecha") or "")
    hora = (request.query_params.get("hora") or "").strip()
    if not parsed_date or hora not in VALID_CLASS_HOURS:
        return RedirectResponse(f"/aula-informatica/en-el-aula/{aula_id}", status_code=303)

    student_ids = parse_student_ids(request.query_params.getlist("student_ids"))

    if not student_ids:
        q = _fecha_hora_query(parsed_date, hora)
        return RedirectResponse(
            f"/aula-informatica/en-el-aula/{aula_id}/sesion?{q}",
            status_code=303,
        )

    return request.app.state.templates.TemplateResponse(
        "aula_informatica/sesion_puestos.html",
        _puestos_page_ctx(
            request,
            user=user,
            aula=aula,
            parsed_date=parsed_date,
            hora=hora,
            student_ids=student_ids,
        ),
    )


@router.post("/en-el-aula/{aula_id}/sesion/puestos", response_class=HTMLResponse)
async def aula_informatica_sesion_puestos_post(
    request: Request,
    aula_id: str,
    session_date: str = Form(...),
    class_hour: str = Form(...),
    student_ids: list[int] = Form(default=[]),
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    aula = get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    parsed_date, hora, session_error = _parse_session_context(
        session_date=session_date,
        class_hour=class_hour,
    )
    if session_error or not parsed_date:
        return RedirectResponse(f"/aula-informatica/en-el-aula/{aula_id}", status_code=303)

    valid_ids = parse_student_ids([str(raw) for raw in student_ids])
    if not valid_ids:
        q = _fecha_hora_query(parsed_date, hora)
        return RedirectResponse(
            f"/aula-informatica/en-el-aula/{aula_id}/sesion?{q}",
            status_code=303,
        )

    allowed = set(valid_ids)
    form = await request.form()
    puestos_rows = parse_puestos_from_form(form, allowed_student_ids=allowed)
    form_error = validate_puestos_rows(puestos_rows, required_student_ids=valid_ids)
    if form_error:
        return request.app.state.templates.TemplateResponse(
            "aula_informatica/sesion_puestos.html",
            _puestos_page_ctx(
                request,
                user=user,
                aula=aula,
                parsed_date=parsed_date,
                hora=hora,
                student_ids=valid_ids,
                form_error=form_error,
                form_state=form_state_from_rows(puestos_rows),
            ),
        )

    draft = build_draft(
        aula_id=aula_id,
        session_date=parsed_date.isoformat(),
        class_hour=hora,
        student_ids=valid_ids,
        puestos_rows=puestos_rows,
    )
    request.session[SESSION_DRAFT_KEY] = draft
    return RedirectResponse(
        f"/aula-informatica/en-el-aula/{aula_id}/sesion/resumen",
        status_code=303,
    )


@router.get("/en-el-aula/{aula_id}/sesion/resumen", response_class=HTMLResponse)
def aula_informatica_sesion_resumen(
    request: Request,
    aula_id: str,
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    aula = get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    draft = request.session.get(SESSION_DRAFT_KEY)
    if not draft or str(draft.get("aula_id") or "") != aula_id:
        return RedirectResponse(f"/aula-informatica/en-el-aula/{aula_id}", status_code=303)

    parsed_date = _parse_session_date(str(draft.get("session_date") or ""))
    if not parsed_date:
        return RedirectResponse(f"/aula-informatica/en-el-aula/{aula_id}", status_code=303)

    return request.app.state.templates.TemplateResponse(
        "aula_informatica/sesion_resumen.html",
        ctx(
            request,
            user=user,
            title=f"Resumen · {aula['label']}",
            nav_section="en_el_aula",
            aula=aula,
            session_date=parsed_date.isoformat(),
            session_date_display=_format_session_date(parsed_date),
            draft=draft,
        ),
    )


@router.post("/en-el-aula/{aula_id}/sesion/resumen/enviar")
def aula_informatica_sesion_resumen_enviar(
    request: Request,
    aula_id: str,
    otras_incidencias: str = Form(""),
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    aula = get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    draft = request.session.get(SESSION_DRAFT_KEY)
    if not draft or str(draft.get("aula_id") or "") != aula_id:
        return RedirectResponse(f"/aula-informatica/en-el-aula/{aula_id}", status_code=303)

    parsed_date = _parse_session_date(str(draft.get("session_date") or ""))
    hora = str(draft.get("class_hour") or "").strip()
    if not parsed_date or hora not in VALID_CLASS_HOURS:
        return RedirectResponse(f"/aula-informatica/en-el-aula/{aula_id}", status_code=303)

    otras = (otras_incidencias or "").strip()
    draft["otras_incidencias"] = otras

    uid = user.get("id")
    if uid is None:
        raise HTTPException(status_code=401, detail="No autenticado")

    report_id = insert_report(
        user_id=int(uid),
        aula_id=aula_id,
        session_date=parsed_date,
        class_hour=hora,
        grupos=list(draft.get("grupos") or []),
        otras_incidencias=otras,
        puestos=[
            {
                "puesto": int(row["puesto"]),
                "student_id": int(row["student_id"]),
                "estado": str(row["estado"]),
                "incidencia": str(row.get("incidencia") or ""),
            }
            for row in draft.get("puestos") or []
        ],
    )
    log_aula_informatica_action(
        user_id=int(uid),
        action="report_create",
        entity_id=report_id,
        detail=(
            f"Informe enviado · {aula['label']} · {parsed_date.isoformat()} · {hora}"
        ),
    )

    request.session.pop(SESSION_DRAFT_KEY, None)
    request.session[SESSION_SENT_KEY] = draft
    return RedirectResponse(
        f"/aula-informatica/en-el-aula/{aula_id}/sesion/enviado",
        status_code=303,
    )


@router.get("/en-el-aula/{aula_id}/sesion/enviado", response_class=HTMLResponse)
def aula_informatica_sesion_enviado(
    request: Request,
    aula_id: str,
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    aula = get_aula(aula_id)
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    sent = request.session.pop(SESSION_SENT_KEY, None)
    if not sent or str(sent.get("aula_id") or "") != aula_id:
        return RedirectResponse("/aula-informatica/dashboard", status_code=303)

    parsed_date = _parse_session_date(str(sent.get("session_date") or ""))
    if not parsed_date:
        return RedirectResponse("/aula-informatica/dashboard", status_code=303)

    return request.app.state.templates.TemplateResponse(
        "aula_informatica/sesion_enviada.html",
        ctx(
            request,
            user=user,
            title=f"Informe enviado · {aula['label']}",
            nav_section="en_el_aula",
            aula=aula,
            session_date=parsed_date.isoformat(),
            session_date_display=_format_session_date(parsed_date),
            draft=sent,
        ),
    )


def _require_user_id(user: dict) -> int:
    uid = user.get("id")
    if uid is None:
        raise HTTPException(status_code=401, detail="No autenticado")
    return int(uid)


@router.get("/mis-registros", response_class=HTMLResponse)
def aula_informatica_mis_registros(request: Request, user: dict = Depends(load_user_dep)):
    _require_access(user)
    uid = _require_user_id(user)
    ok_msg = request.session.pop(SESSION_OK_KEY, None)
    registros = list_reports_for_user(uid)
    for reg in registros:
        aula = get_aula(reg["aula_id"])
        reg["aula_label"] = aula["label"] if aula else reg["aula_id"]
        if reg.get("session_date"):
            reg["session_date_display"] = _format_session_date(reg["session_date"])
    return request.app.state.templates.TemplateResponse(
        "aula_informatica/mis_registros.html",
        ctx(
            request,
            user=user,
            title="Mis registros · Aula de Informática",
            nav_section="mis_registros",
            registros=registros,
            ok_msg=ok_msg,
        ),
    )


@router.get("/mis-registros/{report_id}/editar", response_class=HTMLResponse)
def aula_informatica_mis_registro_editar(
    request: Request,
    report_id: int,
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    uid = _require_user_id(user)
    report = get_report_for_user(int(report_id), uid)
    if not report:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    aula = get_aula(report["aula_id"])
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    parsed_date = _parse_session_date(report.get("session_date") or "")
    if not parsed_date:
        raise HTTPException(status_code=404, detail="Registro no válido")

    return request.app.state.templates.TemplateResponse(
        "aula_informatica/mis_registro_editar.html",
        _mis_registro_editar_ctx(
            request,
            user=user,
            report=report,
            aula=aula,
            parsed_date=parsed_date,
        ),
    )


@router.post("/mis-registros/{report_id}/editar", response_class=HTMLResponse)
async def aula_informatica_mis_registro_editar_post(
    request: Request,
    report_id: int,
    otras_incidencias: str = Form(""),
    student_ids: list[int] = Form(default=[]),
    user: dict = Depends(load_user_dep),
):
    _require_access(user)
    uid = _require_user_id(user)
    report = get_report_for_user(int(report_id), uid)
    if not report:
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    aula = get_aula(report["aula_id"])
    if not aula:
        raise HTTPException(status_code=404, detail="Aula no encontrada")

    parsed_date = _parse_session_date(report.get("session_date") or "")
    if not parsed_date:
        raise HTTPException(status_code=404, detail="Registro no válido")

    valid_ids = parse_student_ids([str(raw) for raw in student_ids])
    if not valid_ids:
        valid_ids = list(report.get("student_ids") or [])

    allowed = set(valid_ids)
    form = await request.form()
    puestos_rows = parse_puestos_from_form(form, allowed_student_ids=allowed)
    form_error = validate_puestos_rows_edit(puestos_rows)
    otras = (otras_incidencias or "").strip()

    if form_error:
        return request.app.state.templates.TemplateResponse(
            "aula_informatica/mis_registro_editar.html",
            _mis_registro_editar_ctx(
                request,
                user=user,
                report=report,
                aula=aula,
                parsed_date=parsed_date,
                form_error=form_error,
                form_state=form_state_from_rows(puestos_rows),
                otras_incidencias=otras,
            ),
        )

    grupos = grupos_from_student_ids(valid_ids)
    if not update_report(
        report_id=int(report_id),
        user_id=uid,
        grupos=grupos,
        otras_incidencias=otras,
        puestos=puestos_rows,
    ):
        raise HTTPException(status_code=404, detail="Registro no encontrado")

    log_aula_informatica_action(
        user_id=uid,
        action="report_update",
        entity_id=int(report_id),
        detail=(
            f"Registro editado · {aula['label']} · "
            f"{parsed_date.isoformat()} · {report.get('class_hour') or ''}"
        ),
    )

    request.session[SESSION_OK_KEY] = "Registro actualizado correctamente."
    return RedirectResponse("/aula-informatica/mis-registros", status_code=303)


@router.get("/registros", response_class=HTMLResponse)
def aula_informatica_registros(
    request: Request,
    aula: str = Query(""),
    user: dict = Depends(load_user_dep),
):
    _require_registros_access(user)
    aula_filter = (aula or "").strip().lower()
    if aula_filter and not get_aula(aula_filter):
        aula_filter = ""
    registros = list_all_reports(aula_id=aula_filter if aula_filter else None)
    puesto_incs = list_puesto_incidencias_for_reports([r["id"] for r in registros])
    for reg in registros:
        aula_obj = get_aula(reg["aula_id"])
        reg["aula_label"] = aula_obj["label"] if aula_obj else reg["aula_id"]
        if reg.get("session_date"):
            reg["session_date_display"] = _format_session_date(reg["session_date"])
        room = get_reservation_room(reg["aula_id"])
        session_d = reg.get("session_date")
        hour = reg.get("class_hour") or ""
        if room and session_d and hour in VALID_CLASS_HOURS:
            reg["tiene_reserva"] = user_has_reservation_for_slot(
                user_id=int(reg["user_id"]),
                room=room,
                d=session_d,
                slot=hour,
            )
        else:
            reg["tiene_reserva"] = False
        reg["reserva_display"] = "Sí" if reg["tiene_reserva"] else "No"

        incidencias_items: list[dict[str, str]] = list(
            puesto_incs.get(int(reg["id"]), [])
        )
        otras = str(reg.get("otras_incidencias") or "").strip()
        if otras:
            incidencias_items.append(
                {"label": "Otras incidencias", "detail": otras}
            )
        reg["incidencias_items"] = incidencias_items
        reg["tiene_incidencias"] = bool(incidencias_items)
        reg["incidencias_display"] = "Sí" if incidencias_items else "No"

    return request.app.state.templates.TemplateResponse(
        "aula_informatica/registros.html",
        ctx(
            request,
            user=user,
            title="Registros · Aula de Informática",
            nav_section="registros",
            registros=registros,
            aula_filter=aula_filter,
            aulas=AULAS_INFORMATICA,
        ),
    )


@router.get("/rastrear", response_class=HTMLResponse)
def aula_informatica_rastrear(request: Request, user: dict = Depends(load_user_dep)):
    _require_rastrear_access(user)
    return request.app.state.templates.TemplateResponse(
        "aula_informatica/rastrear.html",
        ctx(
            request,
            user=user,
            title="Rastrear · Aula de Informática",
            nav_section="rastrear",
            aulas=AULAS_INFORMATICA,
            num_puestos=NUM_PUESTOS,
        ),
    )


@router.get("/rastrear/aula-sesiones", response_class=JSONResponse)
def aula_informatica_rastrear_aula_sesiones(
    aula: str = Query(""),
    user: dict = Depends(load_user_dep),
):
    _require_rastrear_access(user)
    aula_id = (aula or "").strip().lower()
    if not aula_id or not get_aula(aula_id):
        return JSONResponse([])
    sesiones = list_all_reports(aula_id=aula_id)
    payload = []
    for row in sesiones:
        session_date = row.get("session_date")
        payload.append(
            {
                "session_date_display": (
                    _format_session_date(session_date) if session_date else "—"
                ),
                "class_hour": row.get("class_hour") or "—",
                "user_name": row.get("user_name") or "—",
                "grupos_display": row.get("grupos_display") or "—",
            }
        )
    return JSONResponse(payload)


@router.get("/rastrear/puesto-historial", response_class=JSONResponse)
def aula_informatica_rastrear_puesto_historial(
    aula: str = Query(""),
    puesto: int = Query(0),
    user: dict = Depends(load_user_dep),
):
    _require_rastrear_access(user)
    aula_id = (aula or "").strip().lower()
    if not aula_id or not get_aula(aula_id):
        return JSONResponse([])
    if int(puesto) < 1 or int(puesto) > NUM_PUESTOS:
        return JSONResponse([])
    rows = list_puesto_history(aula_id, int(puesto))
    payload = []
    for row in rows:
        session_date = row.get("session_date")
        estado = str(row.get("estado") or "").strip()
        estado_label = "Buen estado" if estado == "buen_estado" else (
            "Incidencias" if estado == "incidencias" else estado or "—"
        )
        payload.append(
            {
                "session_date_display": (
                    _format_session_date(session_date) if session_date else "—"
                ),
                "class_hour": row.get("class_hour") or "—",
                "user_name": row.get("user_name") or "—",
                "alumno": row.get("alumno") or "—",
                "grupo": row.get("grupo") or "—",
                "estado_label": estado_label,
                "incidencia": row.get("incidencia") or "—",
            }
        )
    return JSONResponse(payload)
