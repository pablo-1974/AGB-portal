"""Procedimientos PAA y expedientes disciplinarios."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from auth import load_user_dep
from context import ctx
from db.expedientes_disciplinarios import (
    close_expediente,
    compute_expediente_dias_lectivos,
    create_inicio_expediente,
    delete_expediente,
    get_expediente_by_id,
    list_expedientes_abiertos,
    list_expedientes_cerrados,
    update_expediente,
)
from db.groups import list_groups
from db.paa_procedimientos import (
    create_paa_procedimiento,
    delete_paa_procedimiento,
    get_paa_by_id,
    list_paa_procedimientos,
    update_paa_procedimiento,
)
from db.portal_published_notices import (
    create_expediente_cierre_notice,
    create_expediente_inicio_notice,
    create_paa_notice,
)
from db.students import get_students_by_group, student_exists
from db.users import get_all_teachers
from reservas.calendar import count_school_days
from utils.enums import PERM_SANCIONES
from utils.permissions import has_permission

router = APIRouter(tags=["admin_sanciones"])


def _require_sanciones_access(user):
    if not has_permission(user, PERM_SANCIONES):
        raise HTTPException(status_code=403)


def _parse_date(value: str) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _format_date_display(d: date | None) -> str:
    if d is None:
        return "—"
    return d.strftime("%d/%m/%Y")


def _format_range_display(inicio: date | None, final: date | None) -> str:
    if inicio is None or final is None:
        return "—"
    return f"de {_format_date_display(inicio)} a {_format_date_display(final)}"


def _instructor_options() -> list[dict]:
    return [
        {
            "id": int(t["id"]),
            "name": str(t.get("name") or "").strip(),
        }
        for t in get_all_teachers()
        if str(t.get("name") or "").strip()
    ]


def _paa_row_display(r: dict) -> dict:
    fi = r.get("fecha_inicio")
    ff = r.get("fecha_final")
    ca = r.get("created_at")
    return {
        **r,
        "fecha_inicio_display": _format_date_display(fi if isinstance(fi, date) else None),
        "fecha_final_display": _format_date_display(ff if isinstance(ff, date) else None),
        "fecha_inicio_iso": fi.isoformat() if isinstance(fi, date) else "",
        "fecha_final_iso": ff.isoformat() if isinstance(ff, date) else "",
        "created_at_display": (
            ca.strftime("%d/%m/%Y %H:%M")
            if isinstance(ca, datetime)
            else "—"
        ),
    }


def _paa_page(
    request: Request,
    user: dict,
    *,
    tab: str,
    form: dict | None = None,
    error: str | None = None,
    ok_msg: str | None = None,
    edit_row: dict | None = None,
):
    if tab == "nuevo":
        vista = "nuevo"
    elif tab == "editar":
        vista = "editar"
    else:
        vista = "resumen"

    rows_raw = list_paa_procedimientos() if vista == "resumen" else []
    rows = [_paa_row_display(r) for r in rows_raw]
    edit_display = _paa_row_display(edit_row) if edit_row else None
    form_data = form or {
        "grupo": "",
        "alumno": "",
        "fecha_inicio": "",
        "fecha_final": "",
        "dias_lectivos": "",
    }
    if edit_display and not form:
        form_data = {
            "grupo": str(edit_display.get("grupo") or ""),
            "alumno": str(edit_display.get("alumno") or ""),
            "fecha_inicio": edit_display.get("fecha_inicio_iso") or "",
            "fecha_final": edit_display.get("fecha_final_iso") or "",
            "dias_lectivos": str(edit_display.get("dias_lectivos") or ""),
        }

    dias_preview = ""
    ini = _parse_date(str(form_data.get("fecha_inicio") or ""))
    fin = _parse_date(str(form_data.get("fecha_final") or ""))
    if ini and fin and ini <= fin:
        dias_preview = str(count_school_days(ini, fin))

    return request.app.state.templates.TemplateResponse(
        "admin/sanciones_procedimientos_paa.html",
        ctx(
            request,
            user=user,
            title="Procedimientos PAA",
            tab=vista,
            groups=list_groups(),
            rows=rows,
            form=form_data,
            edit_row=edit_display,
            error=error,
            ok_msg=ok_msg,
            dias_preview=dias_preview,
        ),
    )


@router.get("/admin/sanciones/procedimientos-paa", response_class=HTMLResponse)
def admin_procedimientos_paa(
    request: Request,
    user: dict = Depends(load_user_dep),
    tab: str = "resumen",
    id: str = "",
):
    _require_sanciones_access(user)
    ok_msg = str(request.session.pop("paa_ok_msg", "") or "").strip() or None
    edit_row = None
    if tab == "editar":
        try:
            paa_id = int((id or "").strip())
        except ValueError:
            paa_id = None
        if paa_id is not None:
            edit_row = get_paa_by_id(paa_id)
        if edit_row is None:
            return _paa_page(
                request,
                user,
                tab="resumen",
                ok_msg=ok_msg,
                error="No se encontró el procedimiento PAA a editar.",
            )
    return _paa_page(request, user, tab=tab, ok_msg=ok_msg, edit_row=edit_row)


@router.get("/admin/sanciones/procedimientos-paa/api/alumnos")
def admin_paa_api_alumnos(
    grupo: str = "",
    user: dict = Depends(load_user_dep),
):
    _require_sanciones_access(user)
    g = (grupo or "").strip()
    if not g:
        return []
    return get_students_by_group(g)


@router.get("/admin/sanciones/procedimientos-paa/api/dias-lectivos")
def admin_paa_api_dias_lectivos(
    inicio: str = "",
    fin: str = "",
    user: dict = Depends(load_user_dep),
):
    _require_sanciones_access(user)
    ini = _parse_date(inicio)
    end = _parse_date(fin)
    if not ini or not end:
        return JSONResponse({"dias": None, "error": "Fechas incompletas"})
    if ini > end:
        return JSONResponse(
            {"dias": None, "error": "La fecha inicial no puede ser posterior a la final"}
        )
    return JSONResponse({"dias": count_school_days(ini, end), "error": None})


@router.post("/admin/sanciones/procedimientos-paa", response_class=HTMLResponse)
def admin_procedimientos_paa_create(
    request: Request,
    user: dict = Depends(load_user_dep),
    grupo: str = Form(""),
    alumno: str = Form(""),
    fecha_inicio: str = Form(""),
    fecha_final: str = Form(""),
):
    _require_sanciones_access(user)
    form = {
        "grupo": (grupo or "").strip(),
        "alumno": (alumno or "").strip(),
        "fecha_inicio": (fecha_inicio or "").strip(),
        "fecha_final": (fecha_final or "").strip(),
        "dias_lectivos": "",
    }

    if not form["grupo"] or not form["alumno"]:
        return _paa_page(
            request, user, tab="nuevo", form=form, error="Seleccione grupo y alumno."
        )
    if not student_exists(grupo=form["grupo"], alumno=form["alumno"]):
        return _paa_page(
            request,
            user,
            tab="nuevo",
            form=form,
            error="El alumno no pertenece al grupo indicado.",
        )

    ini = _parse_date(form["fecha_inicio"])
    fin = _parse_date(form["fecha_final"])
    if not ini or not fin:
        return _paa_page(
            request,
            user,
            tab="nuevo",
            form=form,
            error="Indique fecha inicial y fecha final válidas.",
        )
    if ini > fin:
        return _paa_page(
            request,
            user,
            tab="nuevo",
            form=form,
            error="La fecha inicial no puede ser posterior a la final.",
        )

    dias = count_school_days(ini, fin)
    form["dias_lectivos"] = str(dias)
    if dias <= 0:
        return _paa_page(
            request,
            user,
            tab="nuevo",
            form=form,
            error="El rango no incluye ningún día lectivo según el calendario escolar.",
        )

    notice_id = create_paa_notice(
        created_by=user.get("id"),
        alumno_nombre=form["alumno"],
        grupo=form["grupo"],
        fecha_inicio=ini,
        fecha_final=fin,
    )
    create_paa_procedimiento(
        alumno=form["alumno"],
        grupo=form["grupo"],
        fecha_inicio=ini,
        fecha_final=fin,
        dias_lectivos=dias,
        created_by=user.get("id"),
        notice_id=notice_id,
    )
    request.session["paa_ok_msg"] = (
        f"Procedimiento PAA registrado ({dias} día{'s' if dias != 1 else ''} lectivo"
        f"{'s' if dias != 1 else ''}). Se ha publicado el aviso en el portal."
    )
    return RedirectResponse(
        "/admin/sanciones/procedimientos-paa?tab=resumen",
        status_code=303,
    )


@router.post(
    "/admin/sanciones/procedimientos-paa/{paa_id}/editar",
    response_class=HTMLResponse,
)
def admin_procedimientos_paa_editar(
    request: Request,
    paa_id: int,
    user: dict = Depends(load_user_dep),
    fecha_inicio: str = Form(""),
    fecha_final: str = Form(""),
):
    _require_sanciones_access(user)
    row = get_paa_by_id(paa_id)
    if not row:
        return _paa_page(
            request,
            user,
            tab="resumen",
            error="No se encontró el procedimiento PAA a editar.",
        )

    form = {
        "grupo": str(row.get("grupo") or ""),
        "alumno": str(row.get("alumno") or ""),
        "fecha_inicio": (fecha_inicio or "").strip(),
        "fecha_final": (fecha_final or "").strip(),
        "dias_lectivos": "",
    }

    def _err(msg: str):
        return _paa_page(
            request, user, tab="editar", form=form, edit_row=row, error=msg
        )

    ini = _parse_date(form["fecha_inicio"])
    fin = _parse_date(form["fecha_final"])
    if not ini or not fin:
        return _err("Indique fecha inicial y fecha final válidas.")
    if ini > fin:
        return _err("La fecha inicial no puede ser posterior a la final.")

    dias = count_school_days(ini, fin)
    form["dias_lectivos"] = str(dias)
    if dias <= 0:
        return _err(
            "El rango no incluye ningún día lectivo según el calendario escolar."
        )

    try:
        ok = update_paa_procedimiento(
            paa_id=paa_id,
            fecha_inicio=ini,
            fecha_final=fin,
            dias_lectivos=dias,
        )
    except ValueError as e:
        return _err(str(e))
    if not ok:
        return _err("No se pudo actualizar el procedimiento PAA.")

    request.session["paa_ok_msg"] = (
        f"Procedimiento PAA actualizado ({dias} día{'s' if dias != 1 else ''} lectivo"
        f"{'s' if dias != 1 else ''})."
    )
    return RedirectResponse(
        "/admin/sanciones/procedimientos-paa?tab=resumen",
        status_code=303,
    )


@router.post(
    "/admin/sanciones/procedimientos-paa/{paa_id}/borrar",
    response_class=HTMLResponse,
)
def admin_procedimientos_paa_borrar(
    request: Request,
    paa_id: int,
    user: dict = Depends(load_user_dep),
):
    _require_sanciones_access(user)
    ok = delete_paa_procedimiento(paa_id=paa_id)
    if ok:
        request.session["paa_ok_msg"] = "Procedimiento PAA eliminado."
    else:
        request.session["paa_ok_msg"] = "No se encontró el procedimiento PAA a eliminar."
    return RedirectResponse(
        "/admin/sanciones/procedimientos-paa?tab=resumen",
        status_code=303,
    )


def _exp_rows_display(raw_rows: list[dict]) -> list[dict]:
    rows: list[dict] = []
    for r in raw_rows:
        fi = r.get("fecha_inicio_expediente")
        ff = r.get("fecha_final_expediente")
        ci = r.get("cautelar_inicio")
        cf = r.get("cautelar_final")
        si = r.get("sancion_inicio")
        sf = r.get("sancion_final")
        rows.append(
            {
                **r,
                "inicio_expediente_display": _format_date_display(
                    fi if isinstance(fi, date) else None
                ),
                "final_expediente_display": _format_date_display(
                    ff if isinstance(ff, date) else None
                ),
                "fecha_inicio_expediente_iso": (
                    fi.isoformat() if isinstance(fi, date) else ""
                ),
                "fecha_final_expediente_iso": (
                    ff.isoformat() if isinstance(ff, date) else ""
                ),
                "cautelar_inicio_iso": ci.isoformat() if isinstance(ci, date) else "",
                "cautelar_final_iso": cf.isoformat() if isinstance(cf, date) else "",
                "sancion_inicio_iso": si.isoformat() if isinstance(si, date) else "",
                "sancion_final_iso": sf.isoformat() if isinstance(sf, date) else "",
                "cautelar_display": _format_range_display(
                    ci if isinstance(ci, date) else None,
                    cf if isinstance(cf, date) else None,
                ),
                "sancion_display": _format_range_display(
                    si if isinstance(si, date) else None,
                    sf if isinstance(sf, date) else None,
                ),
                "esta_cerrado": ff is not None,
            }
        )
    return rows


def _exp_option_label(r: dict) -> str:
    fi = r.get("fecha_inicio_expediente")
    fi_txt = _format_date_display(fi if isinstance(fi, date) else None)
    return f"{r.get('alumno') or '—'} ({r.get('grupo') or '—'}) — inicio {fi_txt}"


def _exp_page(
    request: Request,
    user: dict,
    *,
    tab: str,
    form: dict | None = None,
    error: str | None = None,
    ok_msg: str | None = None,
    selected_expediente: dict | None = None,
):
    if tab == "nuevo":
        vista = "nuevo"
    elif tab == "cerrar":
        vista = "cerrar"
    elif tab == "editar":
        vista = "editar"
    else:
        vista = "resumen"

    rows_abiertos: list[dict] = []
    rows_cerrados: list[dict] = []
    abiertos_options: list[dict] = []
    if vista == "resumen":
        rows_abiertos = _exp_rows_display(list_expedientes_abiertos())
        rows_cerrados = _exp_rows_display(list_expedientes_cerrados())
    elif vista == "cerrar":
        abiertos_raw = list_expedientes_abiertos()
        abiertos_options = [
            {"id": int(r["id"]), "label": _exp_option_label(r)} for r in abiertos_raw
        ]

    form_data = form or {
        "grupo": "",
        "alumno": "",
        "fecha_inicio_expediente": "",
        "cautelar_inicio": "",
        "cautelar_final": "",
        "instructor_id": "",
        "dias_cautelar": "",
        "expediente_id": "",
        "fecha_final_expediente": "",
        "sancion_inicio": "",
        "sancion_final": "",
        "dias_sancion": "",
    }

    selected_display = None
    if selected_expediente:
        selected_display = _exp_rows_display([selected_expediente])[0]
        if vista == "editar" and not form:
            form_data = {
                "grupo": str(selected_display.get("grupo") or ""),
                "alumno": str(selected_display.get("alumno") or ""),
                "fecha_inicio_expediente": selected_display.get(
                    "fecha_inicio_expediente_iso"
                )
                or "",
                "cautelar_inicio": selected_display.get("cautelar_inicio_iso") or "",
                "cautelar_final": selected_display.get("cautelar_final_iso") or "",
                "instructor_id": (
                    str(selected_display["instructor_id"])
                    if selected_display.get("instructor_id") is not None
                    else ""
                ),
                "dias_cautelar": "",
                "expediente_id": str(selected_display.get("id") or ""),
                "fecha_final_expediente": selected_display.get(
                    "fecha_final_expediente_iso"
                )
                or "",
                "sancion_inicio": selected_display.get("sancion_inicio_iso") or "",
                "sancion_final": selected_display.get("sancion_final_iso") or "",
                "dias_sancion": "",
            }

    caut_ini = _parse_date(str(form_data.get("cautelar_inicio") or ""))
    caut_fin = _parse_date(str(form_data.get("cautelar_final") or ""))
    dias_cautelar_preview = ""
    if caut_ini and caut_fin and caut_ini <= caut_fin:
        dias_cautelar_preview = str(count_school_days(caut_ini, caut_fin))

    san_ini = _parse_date(str(form_data.get("sancion_inicio") or ""))
    san_fin = _parse_date(str(form_data.get("sancion_final") or ""))
    dias_sancion_preview = ""
    if san_ini and san_fin and san_ini <= san_fin:
        dias_sancion_preview = str(count_school_days(san_ini, san_fin))

    return request.app.state.templates.TemplateResponse(
        "admin/sanciones_expedientes_disciplinarios.html",
        ctx(
            request,
            user=user,
            title="Expedientes disciplinarios",
            tab=vista,
            groups=list_groups(),
            instructors=_instructor_options(),
            rows_abiertos=rows_abiertos,
            rows_cerrados=rows_cerrados,
            abiertos_options=abiertos_options,
            selected_expediente=selected_display,
            form=form_data,
            error=error,
            ok_msg=ok_msg,
            dias_cautelar_preview=dias_cautelar_preview,
            dias_sancion_preview=dias_sancion_preview,
        ),
    )


@router.get("/admin/sanciones/expedientes-disciplinarios", response_class=HTMLResponse)
def admin_expedientes_disciplinarios(
    request: Request,
    user: dict = Depends(load_user_dep),
    tab: str = "resumen",
    expediente_id: str = "",
    id: str = "",
):
    _require_sanciones_access(user)
    ok_msg = str(request.session.pop("exp_ok_msg", "") or "").strip() or None
    selected = None
    form = None
    if tab == "cerrar" and (expediente_id or "").strip():
        try:
            eid = int(expediente_id)
        except ValueError:
            eid = None
        if eid is not None:
            row = get_expediente_by_id(eid)
            if row and row.get("fecha_final_expediente") is None:
                selected = row
                form = {
                    "expediente_id": str(eid),
                    "fecha_final_expediente": "",
                    "sancion_inicio": "",
                    "sancion_final": "",
                    "dias_sancion": "",
                }
    elif tab == "editar":
        try:
            eid = int((id or "").strip())
        except ValueError:
            eid = None
        if eid is not None:
            selected = get_expediente_by_id(eid)
        if selected is None:
            return _exp_page(
                request,
                user,
                tab="resumen",
                ok_msg=ok_msg,
                error="No se encontró el expediente a editar.",
            )
    return _exp_page(
        request,
        user,
        tab=tab,
        ok_msg=ok_msg,
        form=form,
        selected_expediente=selected,
    )


@router.get("/admin/sanciones/expedientes-disciplinarios/api/alumnos")
def admin_exp_api_alumnos(
    grupo: str = "",
    user: dict = Depends(load_user_dep),
):
    _require_sanciones_access(user)
    g = (grupo or "").strip()
    if not g:
        return []
    return get_students_by_group(g)


@router.get("/admin/sanciones/expedientes-disciplinarios/api/dias-cautelar")
def admin_exp_api_dias_cautelar(
    cautelar_inicio: str = "",
    cautelar_final: str = "",
    user: dict = Depends(load_user_dep),
):
    _require_sanciones_access(user)
    ci = _parse_date(cautelar_inicio)
    cf = _parse_date(cautelar_final)
    if not ci or not cf:
        return JSONResponse({"dias": None, "error": None})
    if ci > cf:
        return JSONResponse({"dias": None, "error": "Rango inválido"})
    return JSONResponse({"dias": count_school_days(ci, cf), "error": None})


@router.get("/admin/sanciones/expedientes-disciplinarios/api/dias-sancion")
def admin_exp_api_dias_sancion(
    sancion_inicio: str = "",
    sancion_final: str = "",
    user: dict = Depends(load_user_dep),
):
    _require_sanciones_access(user)
    si = _parse_date(sancion_inicio)
    sf = _parse_date(sancion_final)
    if not si or not sf:
        return JSONResponse({"dias": None, "error": None})
    if si > sf:
        return JSONResponse({"dias": None, "error": "Rango inválido"})
    return JSONResponse({"dias": count_school_days(si, sf), "error": None})


@router.post(
    "/admin/sanciones/expedientes-disciplinarios/inicio",
    response_class=HTMLResponse,
)
def admin_expedientes_inicio_create(
    request: Request,
    user: dict = Depends(load_user_dep),
    grupo: str = Form(""),
    alumno: str = Form(""),
    fecha_inicio_expediente: str = Form(""),
    cautelar_inicio: str = Form(""),
    cautelar_final: str = Form(""),
    instructor_id: str = Form(""),
):
    _require_sanciones_access(user)
    form = {
        "grupo": (grupo or "").strip(),
        "alumno": (alumno or "").strip(),
        "fecha_inicio_expediente": (fecha_inicio_expediente or "").strip(),
        "cautelar_inicio": (cautelar_inicio or "").strip(),
        "cautelar_final": (cautelar_final or "").strip(),
        "instructor_id": (instructor_id or "").strip(),
        "dias_cautelar": "",
    }

    def _err(msg: str):
        return _exp_page(request, user, tab="nuevo", form=form, error=msg)

    if not form["grupo"] or not form["alumno"]:
        return _err("Seleccione grupo y alumno.")
    if not student_exists(grupo=form["grupo"], alumno=form["alumno"]):
        return _err("El alumno no pertenece al grupo indicado.")

    ini_exp = _parse_date(form["fecha_inicio_expediente"])
    if not ini_exp:
        return _err("Indique la fecha de inicio del expediente.")

    ci = _parse_date(form["cautelar_inicio"])
    cf = _parse_date(form["cautelar_final"])
    if (ci is None) ^ (cf is None):
        return _err("Indique ambas fechas de la sanción cautelar o déjelas en blanco.")
    if ci is not None and cf is not None and ci > cf:
        return _err("Las fechas de la sanción cautelar no son válidas.")

    if not form["instructor_id"]:
        return _err("Seleccione el instructor del expediente.")
    try:
        instr_id = int(form["instructor_id"])
    except ValueError:
        return _err("Instructor no válido.")
    instructor = next(
        (t for t in _instructor_options() if t["id"] == instr_id),
        None,
    )
    if not instructor:
        return _err("Instructor no válido.")

    dias_cautelar = 0
    if ci is not None and cf is not None:
        dias_cautelar = count_school_days(ci, cf)
        if dias_cautelar <= 0:
            return _err(
                "El rango de sanción cautelar no incluye ningún día lectivo "
                "según el calendario escolar."
            )
    form["dias_cautelar"] = str(dias_cautelar) if dias_cautelar else ""

    notice_id = create_expediente_inicio_notice(
        created_by=user.get("id"),
        alumno_nombre=form["alumno"],
        grupo=form["grupo"],
        fecha_inicio=ini_exp,
        cautelar_inicio=ci,
        cautelar_final=cf,
        dias_cautelar=dias_cautelar if dias_cautelar > 0 else None,
    )
    create_inicio_expediente(
        alumno=form["alumno"],
        grupo=form["grupo"],
        fecha_inicio_expediente=ini_exp,
        cautelar_inicio=ci,
        cautelar_final=cf,
        dias_lectivos=dias_cautelar,
        instructor_id=instr_id,
        instructor_nombre=instructor["name"],
        created_by=user.get("id"),
        notice_id=notice_id,
    )
    request.session["exp_ok_msg"] = (
        "Inicio de expediente registrado. Se ha publicado el aviso en el portal."
    )
    return RedirectResponse(
        "/admin/sanciones/expedientes-disciplinarios?tab=resumen",
        status_code=303,
    )


@router.post(
    "/admin/sanciones/expedientes-disciplinarios/cerrar",
    response_class=HTMLResponse,
)
def admin_expedientes_cerrar(
    request: Request,
    user: dict = Depends(load_user_dep),
    expediente_id: str = Form(""),
    fecha_final_expediente: str = Form(""),
    sancion_inicio: str = Form(""),
    sancion_final: str = Form(""),
):
    _require_sanciones_access(user)
    form = {
        "expediente_id": (expediente_id or "").strip(),
        "fecha_final_expediente": (fecha_final_expediente or "").strip(),
        "sancion_inicio": (sancion_inicio or "").strip(),
        "sancion_final": (sancion_final or "").strip(),
        "dias_sancion": "",
    }

    def _err(msg: str, selected=None):
        return _exp_page(
            request,
            user,
            tab="cerrar",
            form=form,
            error=msg,
            selected_expediente=selected,
        )

    if not form["expediente_id"]:
        return _err("Seleccione un expediente abierto.")
    try:
        eid = int(form["expediente_id"])
    except ValueError:
        return _err("Expediente no válido.")

    exp = get_expediente_by_id(eid)
    if not exp or exp.get("fecha_final_expediente") is not None:
        return _err("El expediente no existe o ya está cerrado.")

    fin = _parse_date(form["fecha_final_expediente"])
    si = _parse_date(form["sancion_inicio"])
    sf = _parse_date(form["sancion_final"])
    if not fin:
        return _err("Indique la fecha de cierre del expediente.", selected=exp)
    if not si or not sf:
        return _err("Indique las fechas de inicio y fin de la sanción.", selected=exp)
    if si > sf:
        return _err("Las fechas de la sanción no son válidas.", selected=exp)

    ini_exp = exp.get("fecha_inicio_expediente")
    if isinstance(ini_exp, date) and fin < ini_exp:
        return _err(
            "La fecha de cierre no puede ser anterior al inicio del expediente.",
            selected=exp,
        )

    dias_sancion = count_school_days(si, sf)
    form["dias_sancion"] = str(dias_sancion)
    if dias_sancion <= 0:
        return _err(
            "El rango de sanción no incluye ningún día lectivo según el calendario escolar.",
            selected=exp,
        )

    ci = exp.get("cautelar_inicio")
    cf = exp.get("cautelar_final")
    dias_cautelar = 0
    if isinstance(ci, date) and isinstance(cf, date):
        dias_cautelar = count_school_days(ci, cf)
    dias_totales = compute_expediente_dias_lectivos(
        cautelar_inicio=ci if isinstance(ci, date) else None,
        cautelar_final=cf if isinstance(cf, date) else None,
        sancion_inicio=si,
        sancion_final=sf,
    )

    notice_id = create_expediente_cierre_notice(
        created_by=user.get("id"),
        alumno_nombre=str(exp.get("alumno") or ""),
        grupo=str(exp.get("grupo") or ""),
        fecha_cierre=fin,
        sancion_inicio=si,
        sancion_final=sf,
        dias_sancion=dias_sancion,
        dias_totales=dias_totales,
        tiene_cautelar=dias_cautelar > 0,
    )
    ok = close_expediente(
        expediente_id=eid,
        fecha_final_expediente=fin,
        sancion_inicio=si,
        sancion_final=sf,
        dias_lectivos=dias_totales,
        notice_cierre_id=notice_id,
    )
    if not ok:
        return _err(
            "No se pudo cerrar el expediente (quizá ya estaba cerrado).", selected=exp
        )

    request.session["exp_ok_msg"] = (
        "Expediente cerrado. Se ha publicado el aviso en el portal."
    )
    return RedirectResponse(
        "/admin/sanciones/expedientes-disciplinarios?tab=resumen",
        status_code=303,
    )


@router.post(
    "/admin/sanciones/expedientes-disciplinarios/{expediente_id}/editar",
    response_class=HTMLResponse,
)
def admin_expedientes_editar(
    request: Request,
    expediente_id: int,
    user: dict = Depends(load_user_dep),
    fecha_inicio_expediente: str = Form(""),
    fecha_final_expediente: str = Form(""),
    cautelar_inicio: str = Form(""),
    cautelar_final: str = Form(""),
    sancion_inicio: str = Form(""),
    sancion_final: str = Form(""),
    instructor_id: str = Form(""),
):
    _require_sanciones_access(user)
    exp = get_expediente_by_id(expediente_id)
    if not exp:
        return _exp_page(
            request,
            user,
            tab="resumen",
            error="No se encontró el expediente a editar.",
        )

    cerrado = exp.get("fecha_final_expediente") is not None
    form = {
        "grupo": str(exp.get("grupo") or ""),
        "alumno": str(exp.get("alumno") or ""),
        "fecha_inicio_expediente": (fecha_inicio_expediente or "").strip(),
        "cautelar_inicio": (cautelar_inicio or "").strip(),
        "cautelar_final": (cautelar_final or "").strip(),
        "instructor_id": (instructor_id or "").strip(),
        "dias_cautelar": "",
        "expediente_id": str(expediente_id),
        "fecha_final_expediente": (fecha_final_expediente or "").strip(),
        "sancion_inicio": (sancion_inicio or "").strip(),
        "sancion_final": (sancion_final or "").strip(),
        "dias_sancion": "",
    }

    def _err(msg: str):
        return _exp_page(
            request,
            user,
            tab="editar",
            form=form,
            error=msg,
            selected_expediente=exp,
        )

    ini_exp = _parse_date(form["fecha_inicio_expediente"])
    if not ini_exp:
        return _err("Indique la fecha de inicio del expediente.")

    ci = _parse_date(form["cautelar_inicio"])
    cf = _parse_date(form["cautelar_final"])
    if (ci is None) ^ (cf is None):
        return _err("Indique ambas fechas de la sanción cautelar o déjelas en blanco.")
    if ci is not None and cf is not None and ci > cf:
        return _err("Las fechas de la sanción cautelar no son válidas.")

    if cerrado:
        fin_exp = _parse_date(form["fecha_final_expediente"])
        si = _parse_date(form["sancion_inicio"])
        sf = _parse_date(form["sancion_final"])
        if not fin_exp:
            return _err("Indique la fecha de cierre del expediente.")
        if not si or not sf:
            return _err("Indique las fechas de inicio y fin de la sanción.")
        if si > sf:
            return _err("Las fechas de la sanción no son válidas.")
        if fin_exp < ini_exp:
            return _err(
                "La fecha de cierre no puede ser anterior al inicio del expediente."
            )
    else:
        fin_exp = None
        si = None
        sf = None

    if not form["instructor_id"]:
        return _err("Seleccione el instructor del expediente.")
    try:
        instr_id = int(form["instructor_id"])
    except ValueError:
        return _err("Instructor no válido.")
    instructor = next(
        (t for t in _instructor_options() if t["id"] == instr_id),
        None,
    )
    if not instructor:
        return _err("Instructor no válido.")

    try:
        dias_totales = compute_expediente_dias_lectivos(
            cautelar_inicio=ci,
            cautelar_final=cf,
            sancion_inicio=si,
            sancion_final=sf,
        )
    except ValueError as e:
        return _err(str(e))

    if ci is not None and cf is not None:
        dias_caut = count_school_days(ci, cf)
        form["dias_cautelar"] = str(dias_caut)
        if dias_caut <= 0:
            return _err(
                "El rango de sanción cautelar no incluye ningún día lectivo "
                "según el calendario escolar."
            )
    if si is not None and sf is not None:
        dias_san = count_school_days(si, sf)
        form["dias_sancion"] = str(dias_san)
        if dias_san <= 0:
            return _err(
                "El rango de sanción no incluye ningún día lectivo "
                "según el calendario escolar."
            )

    try:
        ok = update_expediente(
            expediente_id=expediente_id,
            fecha_inicio_expediente=ini_exp,
            fecha_final_expediente=fin_exp,
            cautelar_inicio=ci,
            cautelar_final=cf,
            sancion_inicio=si,
            sancion_final=sf,
            dias_lectivos=dias_totales,
            instructor_id=instr_id,
            instructor_nombre=instructor["name"],
        )
    except ValueError as e:
        return _err(str(e))
    if not ok:
        return _err("No se pudo actualizar el expediente.")

    request.session["exp_ok_msg"] = "Expediente actualizado."
    return RedirectResponse(
        "/admin/sanciones/expedientes-disciplinarios?tab=resumen",
        status_code=303,
    )


@router.post(
    "/admin/sanciones/expedientes-disciplinarios/{expediente_id}/borrar",
    response_class=HTMLResponse,
)
def admin_expedientes_borrar(
    request: Request,
    expediente_id: int,
    user: dict = Depends(load_user_dep),
):
    _require_sanciones_access(user)
    ok = delete_expediente(expediente_id=expediente_id)
    if ok:
        request.session["exp_ok_msg"] = "Expediente eliminado."
    else:
        request.session["exp_ok_msg"] = "No se encontró el expediente a eliminar."
    return RedirectResponse(
        "/admin/sanciones/expedientes-disciplinarios?tab=resumen",
        status_code=303,
    )
