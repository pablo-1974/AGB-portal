"""Rutas HTTP de Reparto bajo ``/reparto``."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.requests import ClientDisconnect
from urllib.parse import quote

from starlette.concurrency import run_in_threadpool

from context import ctx
from db.departamentos import get_departamento_match, list_departamentos
from db.reparto_loader import RepartoDepartamentoSnapshot
from db.reparto_carga_docente import (
    add_carga_docente,
    catalogo_carga_departamento,
    catalogo_carga_json,
    delete_carga_docente,
    list_carga_docente,
    update_carga_docente,
)
from db.reparto_horas_nominales import (
    add_hora_nominal,
    delete_hora_nominal,
    list_horas_nominales,
    update_hora_nominal,
)
from db.reparto_otros import (
    add_otro,
    delete_otro,
    list_otros,
    update_otro,
)
from db.reparto_repartir_config import (
    MODOS_ELECCION,
    set_modo_eleccion,
)
from db.reparto_miembros import HORAS_JORNADA_COMPLETA, TIPOS_MIEMBRO, exclude_miembro, save_miembros_config
from reparto.cache import clear_reparto_structure_cache
from reparto.deps import require_reparto_access
from reparto.queries import (
    asignar_carga_si_valida,
    asignar_nominal_si_valida,
    asignar_otro_si_valida,
    control_filas,
    deshacer_ultimo_paso_departamento,
    miembros_tabla_departamento,
    reparto_informe_departamento,
    repartir_tabla_departamento,
    saltar_turno_departamento,
    borrar_nominales_departamento,
    borrar_docencia_departamento,
)

router = APIRouter(
    prefix="/reparto",
    tags=["reparto"],
    dependencies=[Depends(require_reparto_access)],
)

RepartoUser = Annotated[dict, Depends(require_reparto_access)]

_CONFIG_VISTAS = frozenset({"miembros", "horas-nominales", "carga-docente", "otros"})


def _fmt_suma(values) -> str:
    total = Decimal(0)
    n = 0
    for v in values:
        raw = str(v or "").strip().replace(",", ".")
        if not raw:
            continue
        try:
            d = Decimal(raw)
        except InvalidOperation:
            continue
        total += d
        n += 1
    if n == 0:
        return ""
    if total == total.to_integral_value():
        return str(int(total))
    return format(total.normalize(), "f").rstrip("0").rstrip(".")


def _templates(request: Request):
    return request.app.state.templates


async def _reparto_form(request: Request) -> dict[str, str] | None:
    """Lee el formulario; None si el cliente cerró la conexión antes de terminar."""
    try:
        raw = await request.form()
        return {str(k): str(v) for k, v in raw.items()}
    except ClientDisconnect:
        return None


def _reparto_disconnect_response(request: Request) -> JSONResponse | RedirectResponse:
    if request.headers.get("X-Reparto-Ajax") == "1":
        return JSONResponse({"ok": False}, status_code=499)
    return RedirectResponse("/reparto/repartir", status_code=303)


def _departamento_sel(raw: str | None) -> dict | None:
    key = (raw or "").strip()
    if not key:
        return None
    return get_departamento_match(key)


def _config_ctx(
    request: Request,
    user: dict,
    *,
    vista: str | None = None,
    departamento_raw: str | None = None,
    nav_section: str = "configuracion",
    extra: dict | None = None,
):
    departamentos = list_departamentos()
    dep = _departamento_sel(departamento_raw)
    payload = {
        "title": "Reparto",
        "nav_section": nav_section,
        "departamentos": departamentos,
        "departamento_sel": dep,
        "departamento_key": (dep.get("abreviatura") if dep else "") or "",
        "vista": vista,
        "horas_jornada_completa": HORAS_JORNADA_COMPLETA,
        "tipos_miembro": TIPOS_MIEMBRO,
    }
    if extra:
        payload.update(extra)
    return ctx(request, user=user, **payload)


def _carga_docente_url(abrev: str) -> str:
    return f"/reparto/configuracion/carga-docente?departamento={quote(abrev, safe='')}"


def _horas_nominales_url(abrev: str) -> str:
    return f"/reparto/configuracion/horas-nominales?departamento={quote(abrev, safe='')}"


def _otros_url(abrev: str) -> str:
    return f"/reparto/configuracion/otros?departamento={quote(abrev, safe='')}"


def _miembros_url(abrev: str) -> str:
    return f"/reparto/configuracion/miembros?departamento={quote(abrev, safe='')}"


def _reparto_ajax_tabla_response(
    request: Request,
    *,
    nom: str,
    abr: str,
    snap: RepartoDepartamentoSnapshot | None,
) -> JSONResponse:
    tabla = repartir_tabla_departamento(
        nombre=nom,
        abreviatura=abr,
        snapshot=snap,
    )
    html = _templates(request).get_template("reparto/_repartir_table.html").render(
        repartir_tabla=tabla,
        departamento_key=abr,
    )
    return JSONResponse(
        {
            "ok": True,
            "turno_nombre": tabla.get("turno_nombre") or "",
            "nominales_completas": bool(tabla.get("nominales_completas")),
            "reparto_completado": bool(tabla.get("reparto_completado")),
            "semaforo_estado": tabla.get("semaforo_estado", "verde"),
            "pasos_pendientes": int(tabla.get("pasos_pendientes") or 0),
            "html": html,
        }
    )


async def _reparto_ajax_tabla_response_async(
    request: Request,
    *,
    nom: str,
    abr: str,
    snap: RepartoDepartamentoSnapshot | None,
) -> JSONResponse:
    return await run_in_threadpool(
        _reparto_ajax_tabla_response,
        request,
        nom=nom,
        abr=abr,
        snap=snap,
    )


def _miembros_extra(dep: dict) -> dict:
    miembros = miembros_tabla_departamento(
        nombre=str(dep.get("departamento") or ""),
        abreviatura=str(dep.get("abreviatura") or ""),
    )
    return {
        "miembros": miembros,
        "n_miembros": len(miembros),
        "total_horas": _fmt_suma(m.get("horas") for m in miembros),
        "vista_title": "Miembros",
        "title": "Reparto · Miembros",
        "vista": "miembros",
    }


@router.get("/", response_class=HTMLResponse)
def reparto_root():
    return RedirectResponse("/reparto/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: RepartoUser):
    return _templates(request).TemplateResponse(
        "reparto/dashboard.html",
        _config_ctx(request, user, nav_section="inicio"),
    )


@router.get("/control", response_class=HTMLResponse)
def control(request: Request, user: RepartoUser):
    response = _templates(request).TemplateResponse(
        "reparto/control.html",
        _config_ctx(
            request,
            user,
            nav_section="control",
            extra={
                "filas": control_filas(),
                "title": "Reparto · Control",
            },
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/repartir", response_class=HTMLResponse)
def repartir(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    dep = _departamento_sel(departamento)
    extra: dict = {
        "title": "Reparto · Repartir",
        "pasos_pendientes": 0,
        "cargar_bordes_async": False,
    }
    if dep:
        tabla = repartir_tabla_departamento(
            nombre=str(dep.get("departamento") or ""),
            abreviatura=str(dep.get("abreviatura") or ""),
            calcular_viabilidad=False,
        )
        grupos_cells = tabla.get("grupos_cells") or []
        pendiente_grupos = any(c.get("pendiente") for c in grupos_cells)
        extra["repartir_tabla"] = tabla
        extra["modos_eleccion"] = MODOS_ELECCION
        extra["modo_eleccion"] = tabla.get("modo_eleccion")
        extra["turno_nombre"] = tabla.get("turno_nombre") or ""
        extra["nominales_completas"] = tabla.get("nominales_completas", False)
        extra["reparto_completado"] = tabla.get("reparto_completado", False)
        extra["semaforo_estado"] = tabla.get("semaforo_estado", "verde")
        extra["pasos_pendientes"] = int(tabla.get("pasos_pendientes") or 0)
        extra["cargar_bordes_async"] = bool(
            tabla.get("nominales_completas")
            and not tabla.get("reparto_completado")
            and pendiente_grupos
        )
    return _templates(request).TemplateResponse(
        "reparto/repartir.html",
        _config_ctx(
            request,
            user,
            nav_section="repartir",
            departamento_raw=departamento,
            extra=extra,
        ),
    )


@router.get("/repartir/bordes", response_class=JSONResponse)
def repartir_bordes_tabla(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    """Viabilidad y bordes del turno (carga lenta diferida tras pintar la tabla)."""
    dep = _departamento_sel(departamento)
    if not dep:
        return JSONResponse({"ok": False, "error": "departamento"}, status_code=400)
    return _reparto_ajax_tabla_response(
        request,
        nom=str(dep.get("departamento") or ""),
        abr=str(dep.get("abreviatura") or ""),
        snap=None,
    )


@router.get("/repartir/resumen", response_class=HTMLResponse)
def repartir_resumen(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    dep = _departamento_sel(departamento)
    if not dep:
        return RedirectResponse("/reparto/repartir", status_code=303)
    abr = str(dep.get("abreviatura") or "")
    nom = str(dep.get("departamento") or "")
    informe = reparto_informe_departamento(nombre=nom, abreviatura=abr)
    if not informe.get("completado"):
        return RedirectResponse(
            f"/reparto/repartir?departamento={quote(abr, safe='')}",
            status_code=303,
        )
    return _templates(request).TemplateResponse(
        "reparto/repartir_resumen.html",
        _config_ctx(
            request,
            user,
            nav_section="repartir",
            departamento_raw=departamento,
            extra={
                "title": "Reparto · Resumen",
                "informe": informe,
            },
        ),
    )


@router.post("/repartir/asignar-nominal", response_class=HTMLResponse)
async def repartir_asignar_nominal(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    form = await _reparto_form(request)
    if form is None:
        return _reparto_disconnect_response(request)
    dep_key = str(form.get("departamento") or departamento or "").strip()
    dep = _departamento_sel(dep_key)
    if not dep:
        return RedirectResponse("/reparto/repartir", status_code=303)
    abr = str(dep.get("abreviatura") or dep_key)
    nom = str(dep.get("departamento") or "")
    try:
        hn_id = int(str(form.get("hora_nominal_id") or "0").strip() or "0")
        uid = int(str(form.get("user_id") or "0").strip() or "0")
    except ValueError:
        hn_id = 0
        uid = 0
    is_ajax = request.headers.get("X-Reparto-Ajax") == "1"
    ok = False
    snap = None
    if hn_id > 0 and uid > 0:
        ok, snap = await run_in_threadpool(
            asignar_nominal_si_valida,
            nombre=nom,
            abreviatura=abr,
            hora_nominal_id=hn_id,
            user_id=uid,
        )
    if is_ajax:
        if not ok:
            return JSONResponse({"ok": False}, status_code=400)
        return await _reparto_ajax_tabla_response_async(
            request, nom=nom, abr=abr, snap=snap
        )
    return RedirectResponse(
        f"/reparto/repartir?departamento={quote(abr, safe='')}",
        status_code=303,
    )


@router.post("/repartir/asignar-otro", response_class=HTMLResponse)
async def repartir_asignar_otro(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    form = await _reparto_form(request)
    if form is None:
        return _reparto_disconnect_response(request)
    dep_key = str(form.get("departamento") or departamento or "").strip()
    dep = _departamento_sel(dep_key)
    if not dep:
        return RedirectResponse("/reparto/repartir", status_code=303)
    abr = str(dep.get("abreviatura") or dep_key)
    nom = str(dep.get("departamento") or "")
    try:
        otro_id = int(str(form.get("otro_id") or "0").strip() or "0")
        uid = int(str(form.get("user_id") or "0").strip() or "0")
    except ValueError:
        otro_id = 0
        uid = 0
    is_ajax = request.headers.get("X-Reparto-Ajax") == "1"
    ok = False
    snap = None
    if otro_id > 0 and uid > 0:
        ok, snap = await run_in_threadpool(
            asignar_otro_si_valida,
            nombre=nom,
            abreviatura=abr,
            otro_id=otro_id,
            user_id=uid,
        )
    if is_ajax:
        if not ok:
            return JSONResponse({"ok": False}, status_code=400)
        return await _reparto_ajax_tabla_response_async(
            request, nom=nom, abr=abr, snap=snap
        )
    return RedirectResponse(
        f"/reparto/repartir?departamento={quote(abr, safe='')}",
        status_code=303,
    )


@router.post("/repartir/asignar-carga", response_class=HTMLResponse)
async def repartir_asignar_carga(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    form = await _reparto_form(request)
    if form is None:
        return _reparto_disconnect_response(request)
    dep_key = str(form.get("departamento") or departamento or "").strip()
    dep = _departamento_sel(dep_key)
    if not dep:
        return RedirectResponse("/reparto/repartir", status_code=303)
    abr = str(dep.get("abreviatura") or dep_key)
    nom = str(dep.get("departamento") or "")
    try:
        carga_id = int(str(form.get("carga_id") or "0").strip() or "0")
        uid = int(str(form.get("user_id") or "0").strip() or "0")
    except ValueError:
        carga_id = 0
        uid = 0
    is_ajax = request.headers.get("X-Reparto-Ajax") == "1"
    ok = False
    snap = None
    if carga_id > 0 and uid > 0:
        ok, snap = await run_in_threadpool(
            asignar_carga_si_valida,
            nombre=nom,
            abreviatura=abr,
            carga_id=carga_id,
            user_id=uid,
        )
    if is_ajax:
        if not ok:
            return JSONResponse({"ok": False}, status_code=400)
        return await _reparto_ajax_tabla_response_async(
            request, nom=nom, abr=abr, snap=snap
        )
    return RedirectResponse(
        f"/reparto/repartir?departamento={quote(abr, safe='')}",
        status_code=303,
    )


@router.post("/repartir/saltar-turno", response_class=HTMLResponse)
async def repartir_saltar_turno(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    form = await _reparto_form(request)
    if form is None:
        return _reparto_disconnect_response(request)
    dep_key = str(form.get("departamento") or departamento or "").strip()
    dep = _departamento_sel(dep_key)
    if not dep:
        return RedirectResponse("/reparto/repartir", status_code=303)
    abr = str(dep.get("abreviatura") or dep_key)
    nom = str(dep.get("departamento") or "")
    is_ajax = request.headers.get("X-Reparto-Ajax") == "1"
    ok, snap = await run_in_threadpool(
        saltar_turno_departamento,
        nombre=nom,
        abreviatura=abr,
    )
    if is_ajax:
        if not ok:
            return JSONResponse({"ok": False}, status_code=400)
        return await _reparto_ajax_tabla_response_async(
            request, nom=nom, abr=abr, snap=snap
        )
    return RedirectResponse(
        f"/reparto/repartir?departamento={quote(abr, safe='')}",
        status_code=303,
    )


@router.post("/repartir/deshacer", response_class=HTMLResponse)
async def repartir_deshacer(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    form = await _reparto_form(request)
    if form is None:
        return _reparto_disconnect_response(request)
    dep_key = str(form.get("departamento") or departamento or "").strip()
    dep = _departamento_sel(dep_key)
    if not dep:
        return RedirectResponse("/reparto/repartir", status_code=303)
    abr = str(dep.get("abreviatura") or dep_key)
    nom = str(dep.get("departamento") or "")
    is_ajax = request.headers.get("X-Reparto-Ajax") == "1"
    ok, snap = await run_in_threadpool(
        deshacer_ultimo_paso_departamento,
        nombre=nom,
        abreviatura=abr,
    )
    if is_ajax:
        if not ok:
            return JSONResponse({"ok": False}, status_code=400)
        return await _reparto_ajax_tabla_response_async(
            request, nom=nom, abr=abr, snap=snap
        )
    return RedirectResponse(
        f"/reparto/repartir?departamento={quote(abr, safe='')}",
        status_code=303,
    )


@router.post("/repartir/borrar-nominales", response_class=HTMLResponse)
async def repartir_borrar_nominales(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    form = await _reparto_form(request)
    if form is None:
        return _reparto_disconnect_response(request)
    dep_key = str(form.get("departamento") or departamento or "").strip()
    dep = _departamento_sel(dep_key)
    if not dep:
        return RedirectResponse("/reparto/repartir", status_code=303)
    abr = str(dep.get("abreviatura") or dep_key)
    nom = str(dep.get("departamento") or "")
    is_ajax = request.headers.get("X-Reparto-Ajax") == "1"
    ok, snap = await run_in_threadpool(
        borrar_nominales_departamento,
        nombre=nom,
        abreviatura=abr,
    )
    if is_ajax:
        if not ok:
            return JSONResponse({"ok": False}, status_code=400)
        return await _reparto_ajax_tabla_response_async(
            request, nom=nom, abr=abr, snap=snap
        )
    return RedirectResponse(
        f"/reparto/repartir?departamento={quote(abr, safe='')}",
        status_code=303,
    )


@router.post("/repartir/borrar-docencia", response_class=HTMLResponse)
async def repartir_borrar_docencia(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    form = await _reparto_form(request)
    if form is None:
        return _reparto_disconnect_response(request)
    dep_key = str(form.get("departamento") or departamento or "").strip()
    dep = _departamento_sel(dep_key)
    if not dep:
        return RedirectResponse("/reparto/repartir", status_code=303)
    abr = str(dep.get("abreviatura") or dep_key)
    nom = str(dep.get("departamento") or "")
    is_ajax = request.headers.get("X-Reparto-Ajax") == "1"
    ok, snap = await run_in_threadpool(
        borrar_docencia_departamento,
        nombre=nom,
        abreviatura=abr,
    )
    if is_ajax:
        if not ok:
            return JSONResponse({"ok": False}, status_code=400)
        return await _reparto_ajax_tabla_response_async(
            request, nom=nom, abr=abr, snap=snap
        )
    return RedirectResponse(
        f"/reparto/repartir?departamento={quote(abr, safe='')}",
        status_code=303,
    )


@router.post("/repartir/modo", response_class=HTMLResponse)
async def repartir_set_modo(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    form = await _reparto_form(request)
    if form is None:
        return _reparto_disconnect_response(request)
    dep_key = str(form.get("departamento") or departamento or "").strip()
    dep = _departamento_sel(dep_key)
    if not dep:
        return RedirectResponse("/reparto/repartir", status_code=303)
    abr = str(dep.get("abreviatura") or dep_key)
    modo = str(form.get("modo_eleccion") or "").strip()
    tabla = repartir_tabla_departamento(
        nombre=str(dep.get("departamento") or ""),
        abreviatura=abr,
    )
    set_modo_eleccion(
        departamento_abrev=abr,
        modo_eleccion=modo,
        filas=tabla.get("filas") or [],
    )
    return RedirectResponse(
        f"/reparto/repartir?departamento={quote(abr, safe='')}",
        status_code=303,
    )


@router.get("/configuracion", response_class=HTMLResponse)
def configuracion(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    return _templates(request).TemplateResponse(
        "reparto/configuracion.html",
        _config_ctx(request, user, departamento_raw=departamento),
    )


@router.get("/configuracion/miembros", response_class=HTMLResponse)
def configuracion_miembros_get(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
):
    dep = _departamento_sel(departamento)
    if not dep:
        return RedirectResponse("/reparto/configuracion", status_code=303)
    return _templates(request).TemplateResponse(
        "reparto/configuracion_miembros.html",
        _config_ctx(
            request,
            user,
            vista="miembros",
            departamento_raw=departamento,
            extra=_miembros_extra(dep),
        ),
    )


@router.post("/configuracion/miembros", response_class=HTMLResponse)
async def configuracion_miembros_save(
    request: Request,
    user: RepartoUser,
):
    form = await request.form()
    departamento = str(form.get("departamento") or "").strip()
    dep = _departamento_sel(departamento)
    if not dep:
        return RedirectResponse("/reparto/configuracion", status_code=303)

    abr = str(dep.get("abreviatura") or departamento)
    borrar_uid = str(form.get("borrar_user_id") or "").strip()
    if borrar_uid:
        try:
            exclude_miembro(departamento_abrev=abr, user_id=int(borrar_uid))
        except ValueError:
            pass
        return RedirectResponse(_miembros_url(abr), status_code=303)

    ids = form.getlist("user_id")
    jornada_ids = {str(x) for x in form.getlist("jornada_completa")}
    no_tutor_ids = {str(x) for x in form.getlist("no_tutor")}
    rows = []
    for raw_id in ids:
        uid = str(raw_id)
        horas_raw = form.get(f"horas_{uid}", HORAS_JORNADA_COMPLETA)
        try:
            horas = int(str(horas_raw).strip() or HORAS_JORNADA_COMPLETA)
        except ValueError:
            horas = HORAS_JORNADA_COMPLETA
        try:
            orden = int(str(form.get(f"orden_{uid}") or "0").strip() or "0")
        except ValueError:
            orden = 0
        tipo = str(form.get(f"tipo_{uid}") or "").strip()
        rows.append(
            {
                "user_id": int(uid),
                "horas": horas,
                "jornada_completa": uid in jornada_ids,
                "no_tutor": uid in no_tutor_ids,
                "tipo": tipo,
                "orden": orden,
            }
        )
    save_miembros_config(departamento_abrev=abr, rows=rows)
    return RedirectResponse(
        f"/reparto/configuracion?departamento={quote(abr, safe='')}",
        status_code=303,
    )


@router.get("/configuracion/horas-nominales", response_class=HTMLResponse)
def configuracion_horas_nominales_get(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
    editar: int | None = None,
):
    dep = _departamento_sel(departamento)
    if not dep:
        return RedirectResponse("/reparto/configuracion", status_code=303)
    abr = str(dep.get("abreviatura") or "")
    filas = list_horas_nominales(abr)
    editar_fila = next((f for f in filas if editar and f["id"] == int(editar)), None)
    return _templates(request).TemplateResponse(
        "reparto/configuracion_horas_nominales.html",
        _config_ctx(
            request,
            user,
            vista="horas-nominales",
            departamento_raw=departamento,
            extra={
                "filas": filas,
                "editar_fila": editar_fila,
                "total_horas": _fmt_suma(f.get("horas_totales") for f in filas),
                "vista_title": "Horas nominales",
                "title": "Reparto · Horas nominales",
            },
        ),
    )


@router.post("/configuracion/horas-nominales", response_class=HTMLResponse)
async def configuracion_horas_nominales_add(
    request: Request,
    user: RepartoUser,
):
    form = await request.form()
    departamento = str(form.get("departamento") or "").strip()
    dep = _departamento_sel(departamento)
    if not dep:
        return RedirectResponse("/reparto/configuracion", status_code=303)
    abr = str(dep.get("abreviatura") or departamento)
    borrar_id = str(form.get("borrar_id") or "").strip()
    if borrar_id:
        try:
            delete_hora_nominal(fila_id=int(borrar_id), departamento_abrev=abr)
        except ValueError:
            pass
        clear_reparto_structure_cache(abr)
        return RedirectResponse(_horas_nominales_url(abr), status_code=303)
    raw_id = str(form.get("fila_id") or "").strip()
    try:
        fila_id = int(raw_id) if raw_id else 0
    except ValueError:
        fila_id = 0
    kwargs = dict(
        departamento_abrev=abr,
        concepto=str(form.get("concepto") or ""),
        grupos=str(form.get("grupos") or ""),
        horas_por_grupo=str(form.get("horas_por_grupo") or ""),
    )
    if fila_id > 0:
        update_hora_nominal(fila_id=fila_id, **kwargs)
    else:
        add_hora_nominal(**kwargs)
    clear_reparto_structure_cache(abr)
    return RedirectResponse(_horas_nominales_url(abr), status_code=303)


@router.get("/configuracion/otros", response_class=HTMLResponse)
def configuracion_otros_get(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
    editar: int | None = None,
):
    dep = _departamento_sel(departamento)
    if not dep:
        return RedirectResponse("/reparto/configuracion", status_code=303)
    abr = str(dep.get("abreviatura") or "")
    filas = list_otros(abr)
    editar_fila = next((f for f in filas if editar and f["id"] == int(editar)), None)
    return _templates(request).TemplateResponse(
        "reparto/configuracion_otros.html",
        _config_ctx(
            request,
            user,
            vista="otros",
            departamento_raw=departamento,
            extra={
                "filas": filas,
                "editar_fila": editar_fila,
                "total_horas": _fmt_suma(f.get("horas_totales") for f in filas),
                "vista_title": "Otros",
                "title": "Reparto · Otros",
            },
        ),
    )


@router.post("/configuracion/otros", response_class=HTMLResponse)
async def configuracion_otros_add(
    request: Request,
    user: RepartoUser,
):
    form = await request.form()
    departamento = str(form.get("departamento") or "").strip()
    dep = _departamento_sel(departamento)
    if not dep:
        return RedirectResponse("/reparto/configuracion", status_code=303)
    abr = str(dep.get("abreviatura") or departamento)
    borrar_id = str(form.get("borrar_id") or "").strip()
    if borrar_id:
        try:
            delete_otro(fila_id=int(borrar_id), departamento_abrev=abr)
        except ValueError:
            pass
        clear_reparto_structure_cache(abr)
        return RedirectResponse(_otros_url(abr), status_code=303)
    raw_id = str(form.get("fila_id") or "").strip()
    try:
        fila_id = int(raw_id) if raw_id else 0
    except ValueError:
        fila_id = 0
    kwargs = dict(
        departamento_abrev=abr,
        concepto=str(form.get("concepto") or ""),
        grupos=str(form.get("grupos") or ""),
        horas_por_grupo=str(form.get("horas_por_grupo") or ""),
    )
    if fila_id > 0:
        update_otro(fila_id=fila_id, **kwargs)
    else:
        add_otro(**kwargs)
    clear_reparto_structure_cache(abr)
    return RedirectResponse(_otros_url(abr), status_code=303)


@router.get("/configuracion/carga-docente", response_class=HTMLResponse)
def configuracion_carga_docente_get(
    request: Request,
    user: RepartoUser,
    departamento: str | None = None,
    editar: int | None = None,
):
    dep = _departamento_sel(departamento)
    if not dep:
        return RedirectResponse("/reparto/configuracion", status_code=303)
    abr = str(dep.get("abreviatura") or "")
    nom = str(dep.get("departamento") or "")
    filas = list_carga_docente(abr)
    editar_fila = next((f for f in filas if editar and f["id"] == int(editar)), None)
    return _templates(request).TemplateResponse(
        "reparto/configuracion_carga_docente.html",
        _config_ctx(
            request,
            user,
            vista="carga-docente",
            departamento_raw=departamento,
            extra={
                "filas": filas,
                "editar_fila": editar_fila,
                "total_horas": _fmt_suma(f.get("horas_totales") for f in filas),
                "catalogo_json": catalogo_carga_json(nombre=nom, abreviatura=abr),
                "vista_title": "Carga docente",
                "title": "Reparto · Carga docente",
            },
        ),
    )


@router.post("/configuracion/carga-docente", response_class=HTMLResponse)
async def configuracion_carga_docente_add(
    request: Request,
    user: RepartoUser,
):
    form = await request.form()
    departamento = str(form.get("departamento") or "").strip()
    dep = _departamento_sel(departamento)
    if not dep:
        return RedirectResponse("/reparto/configuracion", status_code=303)
    abr = str(dep.get("abreviatura") or departamento)
    nom = str(dep.get("departamento") or "")
    catalogo = catalogo_carga_departamento(nombre=nom, abreviatura=abr)
    borrar_id = str(form.get("borrar_id") or "").strip()
    if borrar_id:
        try:
            delete_carga_docente(fila_id=int(borrar_id), departamento_abrev=abr)
        except ValueError:
            pass
        clear_reparto_structure_cache(abr)
        return RedirectResponse(_carga_docente_url(abr), status_code=303)
    raw_id = str(form.get("fila_id") or "").strip()
    try:
        fila_id = int(raw_id) if raw_id else 0
    except ValueError:
        fila_id = 0
    raw_prof = str(form.get("profesores_distintos") or "1").strip()
    try:
        prof_dist = int(raw_prof)
    except ValueError:
        prof_dist = 1
    kwargs = dict(
        departamento_abrev=abr,
        curso_key=str(form.get("curso_key") or ""),
        materia_abrev=str(form.get("materia_abrev") or ""),
        grupos=str(form.get("grupos") or ""),
        tutoria=bool(form.get("tutoria")),
        dc=bool(form.get("dc")),
        catalogo=catalogo,
        horas_por_grupo=str(form.get("horas_por_grupo") or ""),
        profesores_distintos=prof_dist,
    )
    if fila_id > 0:
        update_carga_docente(fila_id=fila_id, **kwargs)
    else:
        add_carga_docente(**kwargs)
    clear_reparto_structure_cache(abr)
    return RedirectResponse(_carga_docente_url(abr), status_code=303)


@router.get("/configuracion/{vista}", response_class=HTMLResponse)
def configuracion_vista(
    request: Request,
    vista: str,
    user: RepartoUser,
    departamento: str | None = None,
):
    if vista == "miembros":
        url = "/reparto/configuracion/miembros"
        if departamento:
            url = _miembros_url(departamento)
        return RedirectResponse(url, status_code=303)
    if vista == "horas-nominales":
        url = "/reparto/configuracion/horas-nominales"
        if departamento:
            url = _horas_nominales_url(departamento)
        return RedirectResponse(url, status_code=303)
    if vista == "carga-docente":
        url = "/reparto/configuracion/carga-docente"
        if departamento:
            url = _carga_docente_url(departamento)
        return RedirectResponse(url, status_code=303)
    if vista == "otros":
        url = "/reparto/configuracion/otros"
        if departamento:
            url = _otros_url(departamento)
        return RedirectResponse(url, status_code=303)
    if vista not in _CONFIG_VISTAS:
        raise HTTPException(status_code=404)
    dep = _departamento_sel(departamento)
    if not dep:
        return RedirectResponse("/reparto/configuracion", status_code=303)

    titles = {
        "otros": "Otros",
    }
    extra = {
        "vista_title": titles[vista],
        "title": f"Reparto · {titles[vista]}",
    }
    return _templates(request).TemplateResponse(
        "reparto/configuracion_placeholder.html",
        _config_ctx(
            request,
            user,
            vista=vista,
            departamento_raw=departamento,
            extra=extra,
        ),
    )
