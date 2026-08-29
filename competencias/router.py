"""Rutas HTTP bajo ``/competencias``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from datetime import date
from urllib.parse import quote, urlencode
import json

from auth import load_user_dep
from competencias.catalogo import (
    ETAPA_BACH,
    ETAPA_ESO,
    ETAPA_LABELS,
    ETAPAS_COMPETENCIAS,
    get_materia_por_clave,
    materias_con_flag_criterios,
)
from context import ctx
from db.competencias_clave import (
    get_competencia_clave,
    list_competencias_clave,
    update_competencia_clave,
)
from db.competencias_evaluacion import (
    NOTAS_ACTA_ESO,
    acta_es_cualitativa,
    compute_nota_comp,
    criterios_codes,
    ensure_competencias_evaluacion_schema,
    format_nota_acta_es,
    format_nota_es,
    format_nota_materia_es,
    list_alumnos_evaluar,
    list_notas_acta,
    list_notas_evaluar,
    parse_evaluacion_workbook,
    parse_nota,
    parse_nota_acta,
    replace_notas_acta,
    replace_notas_evaluar,
    safe_xlsx_filename,
)
from utils.xlsx_export import evaluacion_plantilla_xlsx_bytes
from db.competencias_materia_variables import contexto_ppd_phoras_materia
from db.competencias_pd_porcentajes import (
    criterios_con_porcentajes,
    get_modo_reparto,
    get_mismos_pesos_extra,
    get_mismos_pesos_pendiente,
    materia_puede_ser_pendiente,
    replace_porcentajes_materia,
    resolve_porcentajes_guardar,
    validate_porcentajes_form,
)
from db.competencias_materia_criterios import (
    COMP_CLAVE_COLS,
    build_cruces_matrix,
    list_criterios_materia,
)
from db.departamentos import (
    get_departamento_match,
    user_can_edit_departamento_pd,
    user_can_view_departamento_materias,
    user_ve_todas_materias_competencias,
)
from utils.enums import (
    PERM_COMPETENCIAS_APP,
    PERM_COMPETENCIAS_CALCULOS,
    PERM_COMPETENCIAS_CALIFICAR,
    PERM_COMPETENCIAS_CLAVE,
    PERM_COMPETENCIAS_CONFIG,
    PERM_COMPETENCIAS_EVALUACIONES,
    PERM_COMPETENCIAS_EVALUACIONES_EDIT,
    PERM_COMPETENCIAS_INFORMES,
    PERM_COMPETENCIAS_MATERIAS,
)
from utils.permissions import has_permission, is_invitado
from competencias.normas_data import NORMAS_COMPETENCIAS_SECTIONS
from db.competencias_access import (
    accept_competencias_normas,
    has_accepted_competencias_normas,
)
from competencias.pesos import build_matriz_pesos, list_materias_opciones_pesos
from competencias.variables_doc import variables_por_ambito
from db.competencias_fechas_sesion import (
    grupos_extra_antes_que_ordinaria,
    info_plazo,
    map_fechas_sesion,
    save_fechas_sesion,
)
from db.competencias_pd_edicion import pd_jefes_bloqueados, set_pd_jefes_bloqueados
from db.competencias_calculo_config import (
    get_calculo_config,
    save_calculo_config,
)
from competencias.evaluar_grupos import (
    SESION_LABELS,
    aplicar_excepcionalidad_decision,
    cadena_calculo_alumno,
    datos_pesos_materias_grupo,
    datos_sesion_evaluacion_grupo,
    etapa_del_grupo,
    guardar_nota_sesion_alumno,
    grupos_para_evaluar,
    materia_label_para_evaluar,
    materias_para_evaluar_grupo,
    normalizar_sesion_bach,
    puede_ver_evaluacion_grupo,
    profesor_imparte_grupo,
    profesor_puede_calificar_materia,
    user_ve_todas_evaluaciones,
    user_ve_todo_calificar,
)
from db.groups import group_exists, list_groups_with_course
from db.enrolled_subject_catalog import competencias_materia_group_key
from db.students import get_students_by_group
from db.action_logs import log_competencias_action
from utils.group_stage import extract_course_num, stage_of
from urllib.parse import quote, urlencode

router = APIRouter(prefix="/competencias", tags=["competencias"])


def _require_access(user: dict, permission: str = PERM_COMPETENCIAS_APP) -> None:
    if not has_permission(user, PERM_COMPETENCIAS_APP):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para Evaluación de competencias",
        )
    if permission != PERM_COMPETENCIAS_APP and not has_permission(user, permission):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para esta sección",
        )


def _log_comp(
    user: dict,
    action: str,
    *,
    detail: str | None = None,
    entity: str = "competencias",
    entity_id: int | None = None,
) -> None:
    uid = user.get("id") if user else None
    log_competencias_action(
        user_id=int(uid) if uid is not None else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=detail,
    )


_NAV_PERMISSION = {
    "inicio": PERM_COMPETENCIAS_APP,
    "normas": PERM_COMPETENCIAS_APP,
    "calificar": PERM_COMPETENCIAS_CALIFICAR,
    "sesion-evaluacion": PERM_COMPETENCIAS_EVALUACIONES,
    "cadena": PERM_COMPETENCIAS_CALCULOS,
    "materias": PERM_COMPETENCIAS_MATERIAS,
    "competencias": PERM_COMPETENCIAS_CLAVE,
    "calculos": PERM_COMPETENCIAS_CALCULOS,
    "configuracion": PERM_COMPETENCIAS_CONFIG,
    "informes": PERM_COMPETENCIAS_INFORMES,
}


MSG_PLAZO_CERRADO = (
    "El plazo para introducir calificaciones terminó el día anterior "
    "a la sesión, a las 23:55."
)


def _require_calificar_grupo(user: dict, grupo: str) -> None:
    if not profesor_imparte_grupo(user, grupo):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para calificar este grupo",
        )


def _require_calificar_materia(
    user: dict,
    grupo: str,
    *,
    materia_key: str,
    curso_asignatura: int | None = None,
    pendiente: bool | None = None,
    sesion: str | None = None,
) -> None:
    _require_calificar_grupo(user, grupo)
    if user_ve_todo_calificar(user):
        return
    if not profesor_puede_calificar_materia(
        user,
        grupo,
        materia_key=materia_key,
        curso_asignatura=curso_asignatura,
        pendiente=pendiente,
        sesion=sesion,
    ):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para calificar esta materia",
        )


def _grupos_plano() -> list[str]:
    cols = grupos_para_evaluar()
    out: list[str] = []
    for key in ("eso_12", "eso_34", "bach"):
        out.extend(cols.get(key) or [])
    return out


def _cadena_selector_ctx(
    *,
    grupo: str | None = None,
    alumno: str | None = None,
    sesion: str | None = None,
) -> dict:
    grupos = _grupos_plano()
    grupo_v = (grupo or "").strip()
    if grupo_v and grupo_v not in grupos and group_exists(grupo_v):
        grupos = sorted({*grupos, grupo_v}, key=str.casefold)
    alumnos: list[str] = []
    es_bach = False
    sesion_key = None
    if grupo_v and group_exists(grupo_v):
        alumnos = get_students_by_group(grupo_v)
        stage = etapa_del_grupo(grupo_v)
        es_bach = stage == "bachillerato"
        sesion_key = normalizar_sesion_bach(sesion) if es_bach else None
        if es_bach and not sesion_key:
            sesion_key = "ordinaria"
    return {
        "selector_grupos": grupos,
        "selector_grupo": grupo_v,
        "selector_alumnos": alumnos,
        "selector_alumno": (alumno or "").strip(),
        "selector_es_bach": es_bach,
        "selector_sesion": sesion_key,
    }


def _redirect_plazo_cerrado(data: dict, kind: str) -> RedirectResponse:
    return RedirectResponse(
        f"/competencias/evaluar/{data['grupo']}/{kind}?{data['query_suffix']}"
        f"&status=error&msg={quote(MSG_PLAZO_CERRADO)}",
        status_code=303,
    )


def _page(
    request: Request,
    *,
    user: dict,
    template: str,
    title: str,
    nav_section: str,
    permission: str | None = None,
    **extra,
):
    _require_access(
        user,
        permission
        or _NAV_PERMISSION.get(nav_section, PERM_COMPETENCIAS_APP),
    )
    return request.app.state.templates.TemplateResponse(
        template,
        ctx(
            request,
            user=user,
            title=title,
            portal_shell_title="Evaluación de competencias",
            nav_section=nav_section,
            **extra,
        ),
    )


@router.get("/", include_in_schema=False)
def competencias_root(user: dict = Depends(load_user_dep)):
    _require_access(user)
    return RedirectResponse("/competencias/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse)
def competencias_dashboard(request: Request, user: dict = Depends(load_user_dep)):
    return _page(
        request,
        user=user,
        template="competencias/dashboard.html",
        title="Evaluación de competencias",
        nav_section="inicio",
    )


@router.get("/informes", response_class=HTMLResponse)
def competencias_informes(
    request: Request,
    user: dict = Depends(load_user_dep),
    ambito: str | None = Query(None),
    sel: str | None = Query(None),
):
    ambito_v = (ambito or "grupo").strip().lower()
    if ambito_v not in {"grupo", "curso", "etapa", "centro"}:
        ambito_v = "grupo"
    selected = (sel or "").strip()

    cols = grupos_para_evaluar(user=user, ver_todos=True)
    grupos = [
        *(cols.get("eso_12") or []),
        *(cols.get("eso_34") or []),
        *(cols.get("bach") or []),
    ]
    opciones: list[dict[str, str]] = []
    selector_label = "Selección"
    selector_placeholder = "-- Selecciona --"
    ambito_labels = {
        "grupo": "Grupo",
        "curso": "Curso",
        "etapa": "Etapa",
        "centro": "Centro",
    }

    if ambito_v == "grupo":
        selector_label = "Grupo"
        selector_placeholder = "-- Selecciona grupo --"
        opciones = [{"value": g, "label": g} for g in grupos]
    elif ambito_v == "curso":
        selector_label = "Curso"
        selector_placeholder = "-- Selecciona curso --"
        vistos: set[str] = set()
        for g in list_groups_with_course():
            name = (g.get("name") or "").strip()
            if not name:
                continue
            curso = (g.get("curso") or "").strip() or None
            stage = stage_of(grupo=name, curso=curso)
            if stage not in {"eso", "bachillerato"}:
                continue
            num = extract_course_num(grupo=name, curso=curso, stage=stage)
            if num is None:
                continue
            key = f"{'eso' if stage == 'eso' else 'bach'}:{num}"
            if key in vistos:
                continue
            vistos.add(key)
            label = f"{num}º ESO" if stage == "eso" else f"{num}º Bachillerato"
            opciones.append({"value": key, "label": label})
        opciones.sort(
            key=lambda o: (
                0 if o["value"].startswith("eso:") else 1,
                int(o["value"].split(":")[1]),
            )
        )
    elif ambito_v == "etapa":
        selector_label = "Etapa"
        selector_placeholder = "-- Selecciona etapa --"
        opciones = [
            {"value": "eso", "label": "ESO"},
            {"value": "bachillerato", "label": "Bachillerato"},
        ]
    else:
        selector_label = "Centro"
        selector_placeholder = "-- Selecciona --"
        opciones = [{"value": "centro", "label": "Todo el centro"}]
        # Centro no necesita selector: siempre «Todo el centro».
        selected = "centro"

    if selected and selected not in {o["value"] for o in opciones}:
        selected = ""
    selected_label = next(
        (o["label"] for o in opciones if o["value"] == selected),
        "",
    )

    informe_curso = None
    informe_curso_error = None
    informe_grupo = None
    informe_grupo_error = None
    informe = None
    informe_error = None
    informe_from_cache = False
    vista_v = (request.query_params.get("vista") or "").strip().lower()
    vistas_grupo_curso = {
        "materias",
        "ranking",
        "competencias",
        "decision",
        "alumnos",
    }

    from db.competencias_informes_cache import get_informe_cache, latest_informes_cache_at

    cache_at = latest_informes_cache_at()

    def _load_vista(ambito: str, sel: str, vista: str):
        nonlocal informe_from_cache
        payload, _ts = get_informe_cache(ambito=ambito, sel=sel, vista=vista)
        if payload is not None:
            informe_from_cache = True
            return payload
        return None

    _msg_sin_cache = (
        "No hay datos precalculados. Pulsa Calculadora para generar los informes "
        "y guardarlos; después las vistas cargarán al instante."
    )

    if ambito_v == "curso" and selected:
        if vista_v not in vistas_grupo_curso:
            vista_v = "materias"
        informe = _load_vista("curso", selected, vista_v)
        if informe is None:
            informe_error = _msg_sin_cache
    elif ambito_v == "grupo" and selected:
        if vista_v not in vistas_grupo_curso:
            vista_v = "materias"
        informe = _load_vista("grupo", selected, vista_v)
        if informe is None:
            informe_error = _msg_sin_cache
            informe_grupo_error = informe_error
        else:
            informe_grupo = informe  # compat
    elif ambito_v == "etapa" and selected:
        if vista_v not in {"suspensos_alumno", "suspensos_grupo"}:
            vista_v = "suspensos_alumno"
        informe = _load_vista("etapa", selected, vista_v)
        if informe is None:
            informe_error = _msg_sin_cache
    else:
        vista_v = ""

    calc_status = (request.query_params.get("calc") or "").strip().lower()
    calc_msg = None
    if calc_status == "ok":
        calc_msg = "ok"
    elif calc_status == "error":
        calc_msg = "error"

    return _page(
        request,
        user=user,
        template="competencias/informes.html",
        title="Informes · Evaluación de competencias",
        nav_section="informes",
        ambito=ambito_v,
        ambito_label=ambito_labels[ambito_v],
        opciones=opciones,
        selected=selected,
        selected_label=selected_label,
        selector_label=selector_label,
        selector_placeholder=selector_placeholder,
        vista=vista_v,
        informe=informe,
        informe_error=informe_error,
        informe_curso=informe_curso,
        informe_curso_error=informe_curso_error,
        informe_grupo=informe_grupo,
        informe_grupo_error=informe_grupo_error,
        informes_cache_at=cache_at,
        informe_from_cache=informe_from_cache,
        calc_msg=calc_msg,
        puede_recalcular_informes=user_ve_todo_calificar(user),
    )


@router.post("/informes/recalcular")
def competencias_informes_recalcular(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    _require_access(user, PERM_COMPETENCIAS_INFORMES)
    if not user_ve_todo_calificar(user):
        raise HTTPException(
            status_code=403,
            detail="Solo el equipo directivo puede recalcular los informes.",
        )
    ambito = (request.query_params.get("ambito") or "grupo").strip().lower()
    sel = (request.query_params.get("sel") or "").strip()
    vista = (request.query_params.get("vista") or "").strip()
    try:
        from competencias.informes_data import recalcular_informes_cache

        result = recalcular_informes_cache()
        if result.get("errors") and not result.get("n_ok"):
            q = urlencode(
                {
                    k: v
                    for k, v in {
                        "ambito": ambito,
                        "sel": sel or None,
                        "vista": vista or None,
                        "calc": "error",
                    }.items()
                    if v
                }
            )
            return RedirectResponse(f"/competencias/informes?{q}", status_code=303)
        q = urlencode(
            {
                k: v
                for k, v in {
                    "ambito": ambito,
                    "sel": sel or None,
                    "vista": vista or None,
                    "calc": "ok",
                }.items()
                if v
            }
        )
        return RedirectResponse(f"/competencias/informes?{q}", status_code=303)
    except Exception:
        q = urlencode(
            {
                k: v
                for k, v in {
                    "ambito": ambito,
                    "sel": sel or None,
                    "vista": vista or None,
                    "calc": "error",
                }.items()
                if v
            }
        )
        return RedirectResponse(f"/competencias/informes?{q}", status_code=303)


@router.get("/informes/curso.pdf")
def competencias_informe_curso_pdf(
    user: dict = Depends(load_user_dep),
    sel: str | None = Query(None),
):
    _require_access(user, PERM_COMPETENCIAS_INFORMES)
    from competencias.informes_data import label_curso, parse_curso_sel
    from competencias.informes_pdf import build_informe_grupo_pdf

    parsed = parse_curso_sel(sel or "")
    if not parsed:
        raise HTTPException(status_code=400, detail="Curso no válido")
    try:
        from db.competencias_informes_cache import get_informe_cache

        data, _ = get_informe_cache(ambito="curso", sel=sel or "", vista="completo")
        if data is None:
            raise HTTPException(
                status_code=400,
                detail="No hay datos precalculados. Pulsa Calculadora en Informes.",
            )
        pdf_bytes = build_informe_grupo_pdf(data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc) or "Error al generar PDF") from exc
    etapa, curso_num = parsed
    fname = f"informe_{label_curso(etapa, curso_num).replace(' ', '_').replace('º', '')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.get("/informes/grupo.pdf")
def competencias_informe_grupo_pdf(
    user: dict = Depends(load_user_dep),
    sel: str | None = Query(None),
):
    _require_access(user, PERM_COMPETENCIAS_INFORMES)
    from competencias.informes_pdf import build_informe_grupo_pdf

    nombre = (sel or "").strip()
    if not nombre:
        raise HTTPException(status_code=400, detail="Grupo no indicado")
    try:
        from db.competencias_informes_cache import get_informe_cache

        data, _ = get_informe_cache(ambito="grupo", sel=nombre, vista="completo")
        if data is None:
            raise HTTPException(
                status_code=400,
                detail="No hay datos precalculados. Pulsa Calculadora en Informes.",
            )
        pdf_bytes = build_informe_grupo_pdf(data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc) or "Error al generar PDF") from exc
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in nombre)
    fname = f"informe_grupo_{safe}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.get("/informes/etapa.pdf")
def competencias_informe_etapa_pdf(
    user: dict = Depends(load_user_dep),
    sel: str | None = Query(None),
    vista: str | None = Query(None),
):
    _require_access(user, PERM_COMPETENCIAS_INFORMES)
    etapa = (sel or "").strip().lower()
    if etapa not in {"eso", "bachillerato"}:
        raise HTTPException(status_code=400, detail="Etapa no válida")
    vista_v = (vista or "suspensos_grupo").strip().lower()
    if vista_v != "suspensos_grupo":
        raise HTTPException(
            status_code=400,
            detail="Vista PDF no disponible (usa suspensos_grupo).",
        )
    try:
        from db.competencias_informes_cache import get_informe_cache
        from competencias.informes_pdf import build_informe_etapa_suspensos_grupo_pdf

        data, _ = get_informe_cache(
            ambito="etapa", sel=etapa, vista="suspensos_grupo"
        )
        if data is None:
            raise HTTPException(
                status_code=400,
                detail="No hay datos precalculados. Pulsa Calculadora en Informes.",
            )
        pdf_bytes = build_informe_etapa_suspensos_grupo_pdf(data)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc) or "Error al generar PDF") from exc
    fname = f"informe_etapa_{etapa}_suspensos_grupo.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.get("/informes/centro.pdf")
def competencias_informe_centro_pdf(
    user: dict = Depends(load_user_dep),
    tipo: str | None = Query(None),
):
    _require_access(user, PERM_COMPETENCIAS_INFORMES)
    tipo_v = (tipo or "completo").strip().lower()
    if tipo_v not in {"completo", "resumido"}:
        raise HTTPException(
            status_code=400,
            detail="Tipo no válido (completo o resumido).",
        )
    try:
        from competencias.informes_pdf import build_informe_centro_pdf

        pdf_bytes = build_informe_centro_pdf(include_grupos=(tipo_v == "completo"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc) or "Error al generar PDF") from exc
    fname = f"informe_centro_{tipo_v}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.get("/normas", response_class=HTMLResponse)
def competencias_normas(request: Request, user: dict = Depends(load_user_dep)):
    accepted = is_invitado(user) or has_accepted_competencias_normas(
        user_id=int(user["id"])
    )
    return _page(
        request,
        user=user,
        template="competencias/normas.html",
        title="Normas · Evaluación de competencias",
        nav_section="normas",
        normas_sections=NORMAS_COMPETENCIAS_SECTIONS,
        normas_accepted=accepted,
        normas_pending=not accepted,
    )


@router.post("/normas/aceptar")
def competencias_normas_aceptar(user: dict = Depends(load_user_dep)):
    _require_access(user)
    if not is_invitado(user):
        accept_competencias_normas(user_id=int(user["id"]))
    return RedirectResponse("/competencias/dashboard", status_code=303)


@router.get("/evaluar", response_class=HTMLResponse)
def competencias_evaluar(request: Request, user: dict = Depends(load_user_dep)):
    return _page(
        request,
        user=user,
        template="competencias/evaluar.html",
        title="Calificar · Evaluación de competencias",
        nav_section="calificar",
        columnas=grupos_para_evaluar(user=user),
    )


@router.get("/calificar", include_in_schema=False)
def competencias_calificar_redirect(user: dict = Depends(load_user_dep)):
    _require_access(user, PERM_COMPETENCIAS_CALIFICAR)
    return RedirectResponse("/competencias/evaluar", status_code=303)


@router.get("/sesion-evaluacion", response_class=HTMLResponse)
def competencias_sesion_evaluacion(request: Request, user: dict = Depends(load_user_dep)):
    return _page(
        request,
        user=user,
        template="competencias/sesion_evaluacion.html",
        title="Evaluaciones · Evaluación de competencias",
        nav_section="sesion-evaluacion",
        columnas=grupos_para_evaluar(
            user=user, ver_todos=user_ve_todas_evaluaciones(user)
        ),
        recalc_ok=request.query_params.get("recalc") == "ok",
        puede_editar_evaluacion=has_permission(user, PERM_COMPETENCIAS_EVALUACIONES_EDIT),
    )


@router.post("/sesion-evaluacion/recalcular", response_class=HTMLResponse)
def competencias_sesion_evaluacion_recalcular(user: dict = Depends(load_user_dep)):
    _require_access(user, PERM_COMPETENCIAS_EVALUACIONES_EDIT)
    from db.competencias_alumno_descriptor import sync_all_alumno_descriptor_notas

    sync_all_alumno_descriptor_notas()
    _log_comp(user, "sesion_recalcular", detail="Recálculo de descriptores de todos los alumnos")
    return RedirectResponse(
        "/competencias/sesion-evaluacion?recalc=ok",
        status_code=303,
    )


@router.get("/sesion-evaluacion/{grupo}", response_class=HTMLResponse)
def competencias_sesion_evaluacion_grupo(
    request: Request,
    grupo: str,
    user: dict = Depends(load_user_dep),
    sesion: str | None = Query(None),
):
    nombre = (grupo or "").strip()
    if not nombre or not group_exists(nombre):
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    if not puede_ver_evaluacion_grupo(user, nombre):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para ver esta evaluación",
        )
    stage = etapa_del_grupo(nombre)
    sesion_key = normalizar_sesion_bach(sesion)
    if stage == "bachillerato":
        if not sesion_key:
            raise HTTPException(
                status_code=404,
                detail="Indique la sesión ordinaria o extraordinaria",
            )
        sesion_label = SESION_LABELS[sesion_key]
    else:
        sesion_key = None
        sesion_label = None
    datos = datos_sesion_evaluacion_grupo(nombre, sesion=sesion_key)
    return _page(
        request,
        user=user,
        template="competencias/sesion_evaluacion_grupo.html",
        title=f"Evaluaciones {nombre} · Evaluación de competencias",
        nav_section="sesion-evaluacion",
        grupo=nombre,
        sesion_key=sesion_key,
        sesion_label=sesion_label,
        es_bach=stage == "bachillerato",
        fecha_sesion=datos["fecha_sesion"],
        alumnos=datos["alumnos"],
        competencias=datos["competencias"],
        competencias_clave=datos.get("competencias_clave") or [],
        puede_editar_evaluacion=has_permission(user, PERM_COMPETENCIAS_EVALUACIONES_EDIT),
    )


@router.get("/sesion-evaluacion/{grupo}/pesos-materias")
def competencias_sesion_pesos_materias(
    grupo: str,
    user: dict = Depends(load_user_dep),
    sesion: str | None = Query(None),
):
    """Pesos de materias por CC; solo al abrir Avanzadas → Peso de materias."""
    nombre = (grupo or "").strip()
    if not nombre or not group_exists(nombre):
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    if not puede_ver_evaluacion_grupo(user, nombre):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para ver esta evaluación",
        )
    stage = etapa_del_grupo(nombre)
    sesion_key = normalizar_sesion_bach(sesion) if stage == "bachillerato" else None
    return JSONResponse(datos_pesos_materias_grupo(nombre, sesion=sesion_key))


@router.get("/cadena-alumno", response_class=HTMLResponse)
def competencias_cadena_alumno_hub(
    request: Request,
    user: dict = Depends(load_user_dep),
    grupo: str | None = Query(None),
    alumno: str | None = Query(None),
    sesion: str | None = Query(None),
):
    """Diagnóstico temporal: selector grupo/alumno → cadena de cálculo."""
    _require_access(user, PERM_COMPETENCIAS_CALCULOS)
    grupo_v = (grupo or "").strip()
    alumno_v = (alumno or "").strip()
    if grupo_v and alumno_v and group_exists(grupo_v):
        stage = etapa_del_grupo(grupo_v)
        params: dict[str, str] = {"alumno": alumno_v}
        if stage == "bachillerato":
            sk = normalizar_sesion_bach(sesion) or "ordinaria"
            params["sesion"] = sk
        return RedirectResponse(
            f"/competencias/sesion-evaluacion/{quote(grupo_v)}/cadena-alumno"
            f"?{urlencode(params)}",
            status_code=303,
        )
    ctx = _cadena_selector_ctx(grupo=grupo_v, alumno=alumno_v, sesion=sesion)
    return _page(
        request,
        user=user,
        template="competencias/cadena_alumno.html",
        title="Cadena de cálculo · Evaluación de competencias",
        nav_section="cadena",
        grupo=grupo_v,
        sesion_key=ctx["selector_sesion"],
        datos=None,
        **ctx,
    )


@router.get("/sesion-evaluacion/{grupo}/cadena-alumno", response_class=HTMLResponse)
def competencias_cadena_alumno(
    request: Request,
    grupo: str,
    user: dict = Depends(load_user_dep),
    alumno: str | None = Query(None),
    sesion: str | None = Query(None),
):
    """Diagnóstico: materias → aportaciones → nota_do_* de un alumno."""
    _require_access(user, PERM_COMPETENCIAS_CALCULOS)
    nombre = (grupo or "").strip()
    if not nombre or not group_exists(nombre):
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    alumno_v = (alumno or "").strip()
    stage = etapa_del_grupo(nombre)
    sesion_key = normalizar_sesion_bach(sesion) if stage == "bachillerato" else None
    if stage == "bachillerato" and not sesion_key:
        sesion_key = "ordinaria"
    ctx = _cadena_selector_ctx(grupo=nombre, alumno=alumno_v, sesion=sesion_key)
    if not alumno_v:
        return _page(
            request,
            user=user,
            template="competencias/cadena_alumno.html",
            title=f"Cadena cálculo · {nombre}",
            nav_section="cadena",
            grupo=nombre,
            sesion_key=sesion_key,
            datos=None,
            **ctx,
        )
    try:
        datos = cadena_calculo_alumno(nombre, alumno_v, sesion=sesion_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _page(
        request,
        user=user,
        template="competencias/cadena_alumno.html",
        title=f"Cadena cálculo · {datos['alumno']} · {nombre}",
        nav_section="cadena",
        grupo=nombre,
        sesion_key=sesion_key,
        datos=datos,
        **ctx,
    )


@router.post("/sesion-evaluacion/{grupo}/nota")
async def competencias_sesion_nota_guardar(
    request: Request,
    grupo: str,
    user: dict = Depends(load_user_dep),
    sesion: str | None = Query(None),
):
    _require_access(user, PERM_COMPETENCIAS_EVALUACIONES_EDIT)
    nombre = (grupo or "").strip()
    if not nombre or not group_exists(nombre):
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    stage = etapa_del_grupo(nombre)
    sesion_key = normalizar_sesion_bach(sesion)
    if stage == "bachillerato" and not sesion_key:
        raise HTTPException(status_code=400, detail="Sesión no indicada")
    if stage != "bachillerato":
        sesion_key = None
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="JSON no válido") from exc
    try:
        result = guardar_nota_sesion_alumno(
            grupo=nombre,
            sesion=sesion_key,
            alumno=str(body.get("alumno") or ""),
            scope=str(body.get("scope") or ""),
            scope_key=str(body.get("scope_key") or ""),
            nota_raw=body.get("nota"),
            updated_by=user.get("id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log_comp(
        user,
        "sesion_nota",
        entity="sesion_nota",
        detail=(
            f"{nombre} · {str(body.get('alumno') or '').strip()} · "
            f"{str(body.get('scope') or '').strip()} "
            f"{str(body.get('scope_key') or '').strip()}"
        ),
    )
    return JSONResponse(result)


@router.post("/sesion-evaluacion/{grupo}/promocion-excepcional")
async def competencias_sesion_promocion_excepcional(
    request: Request,
    grupo: str,
    user: dict = Depends(load_user_dep),
    sesion: str | None = Query(None),
):
    _require_access(user, PERM_COMPETENCIAS_EVALUACIONES_EDIT)
    nombre = (grupo or "").strip()
    if not nombre or not group_exists(nombre):
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    stage = etapa_del_grupo(nombre)
    sesion_key = normalizar_sesion_bach(sesion) if stage == "bachillerato" else None
    if stage == "bachillerato" and not sesion_key:
        raise HTTPException(status_code=400, detail="Sesión no indicada")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="JSON no válido") from exc
    try:
        result = aplicar_excepcionalidad_decision(
            grupo=nombre,
            sesion=sesion_key,
            alumno=str(body.get("alumno") or ""),
            excepcionalidad=bool(body.get("excepcionalidad")),
            updated_by=user.get("id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log_comp(
        user,
        "promocion_excepcional",
        entity="promocion",
        detail=(
            f"{nombre} · {sesion_key or 'eso'} · "
            f"{str(body.get('alumno') or '').strip()} · "
            f"excepcionalidad={bool(body.get('excepcionalidad'))}"
        ),
    )
    return JSONResponse(result)


@router.get("/evaluar/{grupo}", response_class=HTMLResponse)
def competencias_evaluar_grupo(
    request: Request,
    grupo: str,
    user: dict = Depends(load_user_dep),
    sesion: str | None = Query(None),
):
    nombre = (grupo or "").strip()
    if not nombre or not group_exists(nombre):
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    _require_calificar_grupo(user, nombre)
    stage = etapa_del_grupo(nombre)
    sesion_key = normalizar_sesion_bach(sesion) if stage == "bachillerato" else None
    sesion_label = SESION_LABELS.get(sesion_key) if sesion_key else None
    if sesion_key == "extraordinaria":
        from db.competencias_bach_ordinaria import ensure_snapshot_ordinaria_grupo

        ensure_snapshot_ordinaria_grupo(nombre)
    return _page(
        request,
        user=user,
        template="competencias/evaluar_grupo.html",
        title=f"Calificar {nombre} · Evaluación de competencias",
        nav_section="calificar",
        grupo=nombre,
        sesion_key=sesion_key,
        sesion_label=sesion_label,
        es_bach_extra=sesion_key == "extraordinaria",
        materias=materias_para_evaluar_grupo(nombre, sesion=sesion_key, user=user),
    )


def _truthy_flag(val: object | None) -> bool:
    if val is True:
        return True
    s = str(val or "").strip().lower()
    return s in ("1", "true", "yes", "on")


def _evaluar_materia_context(
    grupo: str,
    etapa: str | None,
    curso: int | None,
    key: str | None,
    pendiente: str | int | bool | None = None,
    sesion: str | None = None,
    user: dict | None = None,
):
    nombre = (grupo or "").strip()
    if not nombre or not group_exists(nombre):
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    materia_key = (key or "").strip()
    if not materia_key:
        raise HTTPException(status_code=400, detail="Materia no indicada")
    etapa_v = (etapa or "").strip().lower()
    curso_v = int(curso) if curso is not None else None
    materia_label = materia_key
    es_pendiente = _truthy_flag(pendiente)
    if etapa_v and curso_v is not None:
        materia_label = materia_label_para_evaluar(
            etapa=etapa_v,
            curso_asignatura=curso_v,
            materia_key=materia_key,
        )
    else:
        want_pendiente = es_pendiente
        for m in materias_para_evaluar_grupo(
            nombre, sesion=normalizar_sesion_bach(sesion), user=user
        ):
            if (m.get("materia_key") or "") != materia_key:
                continue
            if curso_v is not None and m.get("curso_asignatura") is not None:
                if int(m["curso_asignatura"]) != curso_v:
                    continue
            if pendiente is not None and pendiente != "" and bool(m.get("es_pendiente")) != want_pendiente:
                continue
            materia_label = m.get("materia") or materia_key
            es_pendiente = bool(m.get("es_pendiente"))
            if not etapa_v:
                etapa_v = (m.get("etapa") or "").strip().lower() or etapa_v
            if curso_v is None and m.get("curso_asignatura") is not None:
                curso_v = int(m["curso_asignatura"])
            break
    if not etapa_v or curso_v is None:
        raise HTTPException(
            status_code=400,
            detail="No se pudo determinar etapa y curso de la materia",
        )
    if user is not None:
        _require_calificar_materia(
            user,
            nombre,
            materia_key=materia_key,
            curso_asignatura=curso_v,
            pendiente=es_pendiente,
            sesion=sesion,
        )
    ensure_competencias_evaluacion_schema()
    criterios = criterios_codes(
        etapa=etapa_v,
        curso_asignatura=curso_v,
        materia_key=materia_key,
    )
    alumnos = list_alumnos_evaluar(
        grupo=nombre,
        etapa=etapa_v,
        curso_asignatura=curso_v,
        materia_key=materia_key,
        pendiente=es_pendiente,
    )
    sesion_key = normalizar_sesion_bach(sesion)
    if sesion_key == "extraordinaria" and etapa_v == "bach":
        from db.competencias_bach_ordinaria import (
            ensure_snapshot_ordinaria_grupo,
            mapa_snapshot_ordinaria,
        )
        from competencias.evaluar_grupos import _al, _alumnos_extraordinaria_materia

        ensure_snapshot_ordinaria_grupo(nombre)
        snapshot = mapa_snapshot_ordinaria(nombre)
        meta = {
            "etapa": etapa_v,
            "curso_asignatura": curso_v,
            "materia_key": materia_key,
            "alumnos": {_al(a) for a in alumnos},
        }
        al_extra = _alumnos_extraordinaria_materia(meta, snapshot)
        alumnos = [a for a in alumnos if _al(a) in al_extra]
    notas_raw = list_notas_evaluar(
        etapa=etapa_v,
        curso_asignatura=curso_v,
        materia_key=materia_key,
        grupo=nombre,
        sesion=sesion_key,
    )
    ctx_calc = contexto_ppd_phoras_materia(
        etapa=etapa_v,
        curso_asignatura=curso_v,
        materia_key=materia_key,
        sesion=sesion_key,
        pendiente=es_pendiente,
    )
    ppd_map = ctx_calc["ppd_map"]
    notas: dict[str, dict[str, str]] = {}
    for (al, cr), val in notas_raw.items():
        notas.setdefault(al, {})[cr] = format_nota_es(val)
    notas_comp: dict[str, str] = {}
    for alumno in alumnos:
        por_crit = {
            cr: notas_raw.get((alumno, cr))
            for cr in criterios
        }
        nm = compute_nota_comp(por_crit, ppd_map)
        notas_comp[alumno] = format_nota_materia_es(nm)
    ppd_list = [float(ppd_map[c]) if c in ppd_map else 0.0 for c in criterios]
    qs_params = {
        "etapa": etapa_v,
        "curso": curso_v,
        "key": materia_key,
    }
    if es_pendiente:
        qs_params["pendiente"] = "1"
    if sesion_key:
        qs_params["sesion"] = sesion_key
    qs = urlencode(qs_params)
    return {
        "grupo": nombre,
        "materia_label": materia_label,
        "etapa": etapa_v,
        "curso": curso_v,
        "materia_key": competencias_materia_group_key(materia_key) or materia_key,
        "criterios": criterios,
        "alumnos": alumnos,
        "notas": notas,
        "notas_comp": notas_comp,
        "ppd_json": json.dumps(ppd_list),
        "query_suffix": qs,
        "es_pendiente": es_pendiente,
        "sesion_key": sesion_key,
        "sesion_label": SESION_LABELS.get(sesion_key) if sesion_key else None,
        "es_bach_extra": sesion_key == "extraordinaria",
        **info_plazo(
            grupo=nombre,
            stage=etapa_del_grupo(nombre),
            sesion=sesion_key,
            es_directivo=user_ve_todo_calificar(user) if user else False,
        ),
    }


@router.get("/evaluar/{grupo}/materia", response_class=HTMLResponse)
def competencias_evaluar_materia(
    request: Request,
    grupo: str,
    user: dict = Depends(load_user_dep),
    etapa: str | None = Query(None),
    curso: int | None = Query(None),
    key: str | None = Query(None),
    pendiente: str | None = Query(None),
    sesion: str | None = Query(None),
    status: str | None = Query(None),
    msg: str | None = Query(None),
):
    data = _evaluar_materia_context(
        grupo, etapa, curso, key, pendiente, sesion, user=user
    )
    return _page(
        request,
        user=user,
        template="competencias/evaluar_materia.html",
        title=f"Calificar {data['grupo']} · {data['materia_label']}",
        nav_section="calificar",
        status=status,
        flash_msg=msg,
        **data,
    )


@router.post("/evaluar/{grupo}/materia/guardar")
async def competencias_evaluar_materia_guardar(
    request: Request,
    grupo: str,
    user: dict = Depends(load_user_dep),
    etapa: str = Form(...),
    curso: int = Form(...),
    key: str = Form(...),
    pendiente: str | None = Form(None),
    sesion: str | None = Form(None),
):
    _require_access(user, PERM_COMPETENCIAS_CALIFICAR)
    data = _evaluar_materia_context(
        grupo, etapa, curso, key, pendiente, sesion, user=user
    )
    if not data.get("plazo_abierto", True):
        return _redirect_plazo_cerrado(data, "materia")
    form = await request.form()
    notas_map: dict = {}
    try:
        for i, alumno in enumerate(data["alumnos"]):
            for j, crit in enumerate(data["criterios"]):
                raw = form.get(f"n_{i}_{j}")
                nota = parse_nota(raw)
                if nota is not None:
                    notas_map[(alumno, crit)] = nota
    except ValueError:
        from urllib.parse import quote

        return RedirectResponse(
            f"/competencias/evaluar/{data['grupo']}/materia?{data['query_suffix']}"
            f"&status=error&msg={quote('Solo se admiten notas entre 0 y 10 con hasta 2 decimales.')}",
            status_code=303,
        )
    replace_notas_evaluar(
        etapa=data["etapa"],
        curso_asignatura=data["curso"],
        materia_key=data["materia_key"],
        grupo=data["grupo"],
        notas=notas_map,
        updated_by=user.get("id"),
        sesion=normalizar_sesion_bach(sesion),
        pendiente=bool(data.get("es_pendiente")),
    )
    _log_comp(
        user,
        "notas_materia",
        entity="nota_criterio",
        detail=(
            f"{data['grupo']} · {data.get('materia_label') or data['materia_key']}"
            f"{' · pendiente' if data.get('es_pendiente') else ''}"
        ),
    )
    return RedirectResponse(
        f"/competencias/evaluar/{data['grupo']}/materia?{data['query_suffix']}&status=saved",
        status_code=303,
    )


@router.get("/evaluar/{grupo}/materia/excel")
def competencias_evaluar_materia_excel(
    grupo: str,
    user: dict = Depends(load_user_dep),
    etapa: str | None = Query(None),
    curso: int | None = Query(None),
    key: str | None = Query(None),
    pendiente: str | None = Query(None),
    sesion: str | None = Query(None),
):
    _require_access(user, PERM_COMPETENCIAS_CALIFICAR)
    data = _evaluar_materia_context(
        grupo, etapa, curso, key, pendiente, sesion, user=user
    )
    payload = evaluacion_plantilla_xlsx_bytes(
        grupo=data["grupo"],
        etapa=data["etapa"],
        curso_asignatura=data["curso"],
        materia_key=data["materia_key"],
        materia_label=data["materia_label"],
        criterios=data["criterios"],
        alumnos=data["alumnos"],
    )
    filename = safe_xlsx_filename(
        "evaluar", data["grupo"], data["materia_label"], "blanco"
    )
    return Response(
        payload,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/evaluar/{grupo}/materia/excel")
async def competencias_evaluar_materia_excel_upload(
    grupo: str,
    user: dict = Depends(load_user_dep),
    etapa: str = Form(...),
    curso: int = Form(...),
    key: str = Form(...),
    pendiente: str | None = Form(None),
    sesion: str | None = Form(None),
    file: UploadFile = File(...),
):
    _require_access(user, PERM_COMPETENCIAS_CALIFICAR)
    data = _evaluar_materia_context(
        grupo, etapa, curso, key, pendiente, sesion, user=user
    )
    if not data.get("plazo_abierto", True):
        return _redirect_plazo_cerrado(data, "materia")
    raw = await file.read()
    if not raw:
        return RedirectResponse(
            f"/competencias/evaluar/{data['grupo']}/materia?{data['query_suffix']}"
            f"&status=error&msg=No+se+recibió+ningún+archivo.",
            status_code=303,
        )
    notas, err = parse_evaluacion_workbook(
        raw,
        expected_grupo=data["grupo"],
        expected_etapa=data["etapa"],
        expected_curso=data["curso"],
        expected_materia_key=data["materia_key"],
        expected_criterios=data["criterios"],
    )
    if err or notas is None:
        from urllib.parse import quote

        return RedirectResponse(
            f"/competencias/evaluar/{data['grupo']}/materia?{data['query_suffix']}"
            f"&status=error&msg={quote(err or 'Error al importar.')}",
            status_code=303,
        )
    replace_notas_evaluar(
        etapa=data["etapa"],
        curso_asignatura=data["curso"],
        materia_key=data["materia_key"],
        grupo=data["grupo"],
        notas=notas,
        updated_by=user.get("id"),
        sesion=normalizar_sesion_bach(sesion),
        pendiente=bool(data.get("es_pendiente")),
    )
    _log_comp(
        user,
        "notas_materia_excel",
        entity="nota_criterio",
        detail=(
            f"{data['grupo']} · {data.get('materia_label') or data['materia_key']}"
            f"{' · pendiente' if data.get('es_pendiente') else ''} · Excel"
        ),
    )
    return RedirectResponse(
        f"/competencias/evaluar/{data['grupo']}/materia?{data['query_suffix']}&status=imported",
        status_code=303,
    )


@router.get("/evaluar/{grupo}/acta", response_class=HTMLResponse)
def competencias_evaluar_acta(
    request: Request,
    grupo: str,
    user: dict = Depends(load_user_dep),
    etapa: str | None = Query(None),
    curso: int | None = Query(None),
    key: str | None = Query(None),
    pendiente: str | None = Query(None),
    sesion: str | None = Query(None),
    status: str | None = Query(None),
    msg: str | None = Query(None),
):
    data = _evaluar_materia_context(
        grupo, etapa, curso, key, pendiente, sesion, user=user
    )
    raw = list_notas_acta(
        etapa=data["etapa"],
        curso_asignatura=data["curso"],
        materia_key=data["materia_key"],
        grupo=data["grupo"],
        sesion=normalizar_sesion_bach(sesion),
    )
    cualitativa = acta_es_cualitativa(data.get("etapa"))
    notas_acta = {
        alumno: format_nota_acta_es(raw.get(alumno), cualitativa=cualitativa)
        for alumno in data["alumnos"]
    }
    return _page(
        request,
        user=user,
        template="competencias/evaluar_acta.html",
        title=f"nota_acta {data['grupo']} · {data['materia_label']}",
        nav_section="calificar",
        status=status,
        flash_msg=msg,
        notas_acta=notas_acta,
        acta_cualitativa=cualitativa,
        notas_acta_eso=NOTAS_ACTA_ESO,
        **{k: v for k, v in data.items() if k != "notas_comp"},
    )


@router.post("/evaluar/{grupo}/acta/guardar")
async def competencias_evaluar_acta_guardar(
    request: Request,
    grupo: str,
    user: dict = Depends(load_user_dep),
    etapa: str = Form(...),
    curso: int = Form(...),
    key: str = Form(...),
    pendiente: str | None = Form(None),
    sesion: str | None = Form(None),
):
    _require_access(user, PERM_COMPETENCIAS_CALIFICAR)
    data = _evaluar_materia_context(
        grupo, etapa, curso, key, pendiente, sesion, user=user
    )
    if not data.get("plazo_abierto", True):
        return _redirect_plazo_cerrado(data, "acta")
    form = await request.form()
    notas_map: dict = {}
    cualitativa = acta_es_cualitativa(data.get("etapa"))
    try:
        for i, alumno in enumerate(data["alumnos"]):
            notas_map[alumno] = parse_nota_acta(
                form.get(f"n_{i}"), cualitativa=cualitativa
            )
    except ValueError:
        from urllib.parse import quote

        err = (
            "nota_acta de ESO debe ser IN, SU, BI, NT o SB."
            if cualitativa
            else "nota_acta solo admite enteros del 0 al 10."
        )
        return RedirectResponse(
            f"/competencias/evaluar/{data['grupo']}/acta?{data['query_suffix']}"
            f"&status=error&msg={quote(err)}",
            status_code=303,
        )
    replace_notas_acta(
        etapa=data["etapa"],
        curso_asignatura=data["curso"],
        materia_key=data["materia_key"],
        grupo=data["grupo"],
        notas=notas_map,
        updated_by=user.get("id"),
        sesion=normalizar_sesion_bach(sesion),
    )
    _log_comp(
        user,
        "notas_acta",
        entity="nota_acta",
        detail=f"{data['grupo']} · {data.get('materia_label') or data['materia_key']}",
    )
    return RedirectResponse(
        f"/competencias/evaluar/{data['grupo']}/acta?{data['query_suffix']}&status=saved",
        status_code=303,
    )


@router.get("/configuracion", response_class=HTMLResponse)
def competencias_configuracion(request: Request, user: dict = Depends(load_user_dep)):
    return _page(
        request,
        user=user,
        template="competencias/configuracion.html",
        title="Configuración · Evaluación de competencias",
        nav_section="configuracion",
    )


def _filas_fechas_config() -> dict[str, list[dict]]:
    columnas = grupos_para_evaluar()
    fechas = map_fechas_sesion()

    def iso_of(grupo: str, sesion: str) -> str:
        fd = fechas.get((grupo, sesion)) or fechas.get((grupo.casefold(), sesion))
        return fd.isoformat() if fd else ""

    def filas_eso(grupos: list[str]) -> list[dict]:
        return [
            {"grupo": g, "sesion": "", "fecha_iso": iso_of(g, "")}
            for g in grupos
        ]

    bach: list[dict] = []
    for g in columnas.get("bach") or []:
        iso_ord = iso_of(g, "ordinaria")
        bach.append(
            {
                "grupo": g,
                "sesion": "ordinaria",
                "sesion_label": "Ordinaria",
                "fecha_iso": iso_ord,
            }
        )
        bach.append(
            {
                "grupo": g,
                "sesion": "extraordinaria",
                "sesion_label": "Extraordinaria",
                "fecha_iso": iso_of(g, "extraordinaria"),
                "min_iso": iso_ord,
            }
        )
    return {
        "eso_12": filas_eso(columnas.get("eso_12") or []),
        "eso_34": filas_eso(columnas.get("eso_34") or []),
        "bach": bach,
    }


@router.get("/configuracion/fechas-evaluaciones", response_class=HTMLResponse)
def competencias_config_fechas(
    request: Request,
    user: dict = Depends(load_user_dep),
    status: str | None = Query(None),
):
    return _page(
        request,
        user=user,
        template="competencias/configuracion_fechas.html",
        title="Fechas de evaluaciones · Evaluación de competencias",
        nav_section="configuracion",
        columnas=_filas_fechas_config(),
        status=status,
    )


@router.post("/configuracion/fechas-evaluaciones")
async def competencias_config_fechas_guardar(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    _require_access(user, PERM_COMPETENCIAS_CONFIG)
    form = await request.form()
    try:
        n_filas = int(str(form.get("n_filas") or "0"))
    except ValueError:
        n_filas = 0
    items: list[tuple[str, str, date | None]] = []
    for i in range(max(0, min(n_filas, 200))):
        grupo = str(form.get(f"g_{i}") or "").strip()
        if not grupo:
            continue
        sesion = str(form.get(f"s_{i}") or "").strip()
        raw = str(form.get(f"f_{i}") or "").strip()
        fecha: date | None = None
        if raw:
            try:
                fecha = date.fromisoformat(raw)
            except ValueError:
                fecha = None
        items.append((grupo, sesion, fecha))
    conflictos = grupos_extra_antes_que_ordinaria(items)
    if conflictos:
        columnas = _filas_fechas_config()
        overlay: dict[tuple[str, str], date | None] = {}
        for grupo, sesion, fecha in items:
            overlay[((grupo or "").strip(), (sesion or "").strip().lower())] = fecha
        for filas in columnas.values():
            for row in filas:
                key = ((row.get("grupo") or "").strip(), (row.get("sesion") or "").strip().lower())
                if key not in overlay:
                    continue
                fd = overlay[key]
                row["fecha_iso"] = fd.isoformat() if fd else ""
        for i, row in enumerate(columnas.get("bach") or []):
            if (row.get("sesion") or "") != "extraordinaria":
                continue
            prev = (columnas["bach"][i - 1] if i else None) or {}
            if (prev.get("grupo") or "") == (row.get("grupo") or "") and (
                prev.get("sesion") or ""
            ) == "ordinaria":
                row["min_iso"] = prev.get("fecha_iso") or ""
        nombres = ", ".join(conflictos)
        return _page(
            request,
            user=user,
            template="competencias/configuracion_fechas.html",
            title="Fechas de evaluaciones · Evaluación de competencias",
            nav_section="configuracion",
            columnas=columnas,
            status="error",
            error_msg=(
                "La extraordinaria no puede ser anterior a la ordinaria "
                f"({nombres})."
            ),
        )
    save_fechas_sesion(items)
    _log_comp(
        user,
        "fechas_evaluaciones",
        entity="fechas_sesion",
        detail=f"{len(items)} grupo(s)",
    )
    return RedirectResponse(
        "/competencias/configuracion/fechas-evaluaciones?status=saved",
        status_code=303,
    )


@router.get("/configuracion/calculo-competencias", response_class=HTMLResponse)
def competencias_config_calculo(
    request: Request,
    user: dict = Depends(load_user_dep),
    status: str | None = Query(None),
):
    return _page(
        request,
        user=user,
        template="competencias/configuracion_calculo.html",
        title="Cálculo de competencias · Evaluación de competencias",
        nav_section="configuracion",
        cfg=get_calculo_config(),
        status=status,
    )


@router.post("/configuracion/calculo-competencias")
async def competencias_config_calculo_guardar(
    request: Request,
    user: dict = Depends(load_user_dep),
):
    _require_access(user, PERM_COMPETENCIAS_CONFIG)
    form = await request.form()
    save_calculo_config(
        promedio_descriptores=str(form.get("promedio_descriptores") or ""),
        peso_periodos=str(form.get("peso_periodos") or ""),
        tratamiento_pendientes=str(form.get("tratamiento_pendientes") or ""),
        decimales=str(form.get("decimales") or ""),
    )
    _log_comp(user, "calculo_config", entity="calculo_config", detail="Configuración de cálculo")
    return RedirectResponse(
        "/competencias/configuracion/calculo-competencias?status=saved",
        status_code=303,
    )


@router.get("/calculos", response_class=HTMLResponse)
def competencias_calculos(request: Request, user: dict = Depends(load_user_dep)):
    if not (
        has_permission(user, PERM_COMPETENCIAS_CALCULOS)
        or has_permission(user, PERM_COMPETENCIAS_CLAVE)
    ):
        raise HTTPException(status_code=403, detail="Sin permiso para esta sección")
    return _page(
        request,
        user=user,
        template="competencias/calculos.html",
        title="Cálculos · Evaluación de competencias",
        nav_section="calculos",
        permission=PERM_COMPETENCIAS_APP,
    )


@router.get("/calculos/variables", response_class=HTMLResponse)
def competencias_calculos_variables(
    request: Request, user: dict = Depends(load_user_dep)
):
    return _page(
        request,
        user=user,
        template="competencias/variables.html",
        title="Variables de cálculo · Evaluación de competencias",
        nav_section="calculos",
        grupos=variables_por_ambito(),
    )


@router.get("/calculos/pesos", response_class=HTMLResponse)
def competencias_calculos_pesos(
    request: Request,
    user: dict = Depends(load_user_dep),
    etapa: str | None = Query(None),
    curso: int | None = Query(None),
    key: str | None = Query(None),
    var: str | None = Query(None),
):
    from competencias.pesos import VARIABLES_PESO

    etapa_sel = (etapa or "").strip().lower() or None
    key_sel = (key or "").strip() or None
    curso_sel = int(curso) if curso is not None else None
    var_sel = (var or "").strip().lower() or None
    if var_sel not in ("coef0", "coef1", "coef2"):
        var_sel = None
    matriz = None
    if etapa_sel and key_sel and curso_sel is not None:
        if etapa_sel in ETAPAS_COMPETENCIAS:
            matriz = build_matriz_pesos(
                etapa=etapa_sel,
                curso_asignatura=curso_sel,
                materia_key=key_sel,
                variable=var_sel,
            )
    return _page(
        request,
        user=user,
        template="competencias/calculos_pesos.html",
        title="Pesos · Evaluación de competencias",
        nav_section="calculos",
        materias_opciones=list_materias_opciones_pesos(),
        matriz=matriz,
        etapa_sel=etapa_sel,
        curso_sel=curso_sel,
        key_sel=key_sel,
        var_sel=var_sel,
        variables_peso=VARIABLES_PESO,
    )


@router.get("/variables", include_in_schema=False)
def competencias_variables_redirect(user: dict = Depends(load_user_dep)):
    _require_access(user, PERM_COMPETENCIAS_CALCULOS)
    return RedirectResponse("/competencias/calculos/variables", status_code=303)


@router.get("/materias", response_class=HTMLResponse)
def competencias_materias(
    request: Request,
    user: dict = Depends(load_user_dep),
    etapa: str | None = Query(None),
    curso: str | None = Query(None),
    departamento: str | None = Query(None),
):
    etapa_sel = (etapa or "").strip().lower() or None
    if etapa_sel and etapa_sel not in ETAPAS_COMPETENCIAS:
        etapa_sel = None

    ve_todas = user_ve_todas_materias_competencias(user)
    materias = materias_con_flag_criterios(etapa_sel) if etapa_sel else []
    if not ve_todas:
        materias = [
            m
            for m in materias
            if user_can_view_departamento_materias(user, m.get("departamento"))
        ]

    cursos_filtro = sorted(
        {int(m["curso_asignatura"]) for m in materias if m.get("curso_asignatura") is not None}
    )
    curso_sel: int | None = None
    raw_curso = (curso or "").strip()
    if raw_curso:
        try:
            parsed = int(raw_curso)
            if parsed in cursos_filtro:
                curso_sel = parsed
        except ValueError:
            curso_sel = None
    if curso_sel is not None:
        materias = [
            m for m in materias if int(m.get("curso_asignatura") or 0) == curso_sel
        ]

    departamentos_filtro = sorted(
        {
            (m.get("departamento") or "").strip()
            for m in materias
            if (m.get("departamento") or "").strip()
        },
        key=str.casefold,
    )
    departamento_sel = (departamento or "").strip()
    if not ve_todas and departamentos_filtro and not departamento_sel:
        # Un solo departamento visible: fijar filtro para la UI.
        if len(departamentos_filtro) == 1:
            departamento_sel = departamentos_filtro[0]
    if departamento_sel:
        dep_key = departamento_sel.casefold()
        materias = [
            m
            for m in materias
            if (m.get("departamento") or "").strip().casefold() == dep_key
        ]
    return _page(
        request,
        user=user,
        template="competencias/materias.html",
        title="Materias · Evaluación de competencias",
        nav_section="materias",
        etapa_sel=etapa_sel,
        etapa_eso=ETAPA_ESO,
        etapa_bach=ETAPA_BACH,
        etapa_label=ETAPA_LABELS.get(etapa_sel or "", ""),
        materias=materias,
        cursos_filtro=cursos_filtro,
        curso_sel=curso_sel,
        departamentos_filtro=departamentos_filtro,
        departamento_sel=departamento_sel,
        ve_todas_materias=ve_todas,
        puede_bloquear_pd=user_ve_todo_calificar(user),
        pd_jefes_bloqueados=pd_jefes_bloqueados() if user_ve_todo_calificar(user) else False,
    )


@router.post("/materias/bloquear-pd")
async def competencias_materias_bloquear_pd(
    request: Request,
    user: dict = Depends(load_user_dep),
    etapa: str | None = Query(None),
    curso: str | None = Query(None),
    departamento: str | None = Query(None),
):
    _require_access(user, PERM_COMPETENCIAS_MATERIAS)
    if not user_ve_todo_calificar(user):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para bloquear la edición de porcentajes",
        )
    form = await request.form()
    bloquear = str(form.get("bloquear") or "").strip() == "1"
    set_pd_jefes_bloqueados(bloquear)
    _log_comp(
        user,
        "bloquear_pd",
        entity="pd",
        detail="Bloquear edición PD jefes" if bloquear else "Desbloquear edición PD jefes",
    )
    qs = []
    if (etapa or "").strip():
        qs.append(f"etapa={quote((etapa or '').strip())}")
    if (curso or "").strip():
        qs.append(f"curso={quote((curso or '').strip())}")
    if (departamento or "").strip():
        qs.append(f"departamento={quote((departamento or '').strip())}")
    suffix = f"?{'&'.join(qs)}" if qs else ""
    return RedirectResponse(f"/competencias/materias{suffix}", status_code=303)


@router.get("/materias/detalle", response_class=HTMLResponse)
def competencias_materia_detalle(
    request: Request,
    user: dict = Depends(load_user_dep),
    etapa: str = Query(...),
    curso: int = Query(...),
    key: str = Query(...),
):
    etapa_sel = (etapa or "").strip().lower()
    if etapa_sel not in ETAPAS_COMPETENCIAS:
        raise HTTPException(status_code=404, detail="Etapa no válida")

    materia = get_materia_por_clave(
        etapa=etapa_sel,
        curso_asignatura=curso,
        materia_key=key,
    )
    # Si no está en el catálogo Neon, aún puede haber criterios sembrados.
    criterios = list_criterios_materia(
        etapa=etapa_sel,
        curso_asignatura=curso,
        materia_key=key,
    )
    if not materia and not criterios:
        raise HTTPException(status_code=404, detail="Materia no encontrada")

    nombre = (materia or {}).get("materia") or (
        criterios[0].get("materia_nombre") if criterios else key
    )
    departamento_ref = (materia or {}).get("departamento")
    dep_row = get_departamento_match(departamento_ref)
    departamento_label = (
        (dep_row or {}).get("departamento")
        or (departamento_ref or "").strip()
        or None
    )
    if not user_can_view_departamento_materias(user, departamento_ref):
        raise HTTPException(
            status_code=403,
            detail="Solo puedes consultar las materias de tu departamento",
        )
    can_edit_pd = user_can_edit_departamento_pd(user, departamento_ref)
    pct_rows = criterios_con_porcentajes(
        etapa=etapa_sel,
        curso_asignatura=curso,
        materia_key=key,
    )
    cruces = build_cruces_matrix(criterios)
    return _page(
        request,
        user=user,
        template="competencias/materia_detalle.html",
        title=f"{nombre} · Materias",
        nav_section="materias",
        etapa_sel=etapa_sel,
        etapa_label=ETAPA_LABELS.get(etapa_sel, etapa_sel),
        curso=curso,
        materia_nombre=nombre,
        materia_key=key,
        departamento=departamento_label,
        can_edit_pd=can_edit_pd,
        pct_rows=pct_rows,
        modo_pd=get_modo_reparto(
            etapa=etapa_sel,
            curso_asignatura=curso,
            materia_key=key,
            criterios_rows=criterios,
        ),
        mismos_pesos_extra=get_mismos_pesos_extra(
            etapa=etapa_sel,
            curso_asignatura=curso,
            materia_key=key,
        ),
        mismos_pesos_pendiente=get_mismos_pesos_pendiente(
            etapa=etapa_sel,
            curso_asignatura=curso,
            materia_key=key,
        ),
        puede_ser_pendiente=materia_puede_ser_pendiente(etapa_sel, curso),
        criterios=criterios,
        cruces=cruces,
        comp_cols=COMP_CLAVE_COLS,
        pd_saved=request.query_params.get("pd") == "saved",
        pd_error=request.query_params.get("pd_error"),
    )


@router.post("/materias/detalle/porcentajes-pd", response_class=HTMLResponse)
async def competencias_materia_guardar_pd(
    request: Request,
    user: dict = Depends(load_user_dep),
    etapa: str = Query(...),
    curso: int = Query(...),
    key: str = Query(...),
):
    _require_access(user, PERM_COMPETENCIAS_MATERIAS)
    etapa_sel = (etapa or "").strip().lower()
    if etapa_sel not in ETAPAS_COMPETENCIAS:
        raise HTTPException(status_code=404, detail="Etapa no válida")

    materia = get_materia_por_clave(
        etapa=etapa_sel,
        curso_asignatura=curso,
        materia_key=key,
    )
    departamento_ref = (materia or {}).get("departamento")
    if not user_can_view_departamento_materias(user, departamento_ref):
        raise HTTPException(
            status_code=403,
            detail="Solo puedes consultar las materias de tu departamento",
        )
    if not user_can_edit_departamento_pd(user, departamento_ref):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para editar los porcentajes de la PD",
        )

    criterios = list_criterios_materia(
        etapa=etapa_sel,
        curso_asignatura=curso,
        materia_key=key,
    )
    crit_codes = [str(c.get("criterio") or "").strip() for c in criterios]
    crit_codes = [c for c in crit_codes if c]
    if not crit_codes:
        raise HTTPException(status_code=400, detail="No hay criterios para esta materia")

    form = await request.form()
    form_values = {str(k): form.get(k) for k in form.keys()}
    modo = str(form_values.get("modo_reparto") or "libre")
    parsed, error = resolve_porcentajes_guardar(
        modo=modo,
        criterios_rows=criterios,
        form_values=form_values,
    )
    mismos_pesos = True
    parsed_extra = None
    if etapa_sel == ETAPA_BACH:
        mismos_pesos = str(form_values.get("mismos_pesos_extra") or "").strip() in (
            "1",
            "on",
            "true",
            "yes",
        )
        if not mismos_pesos and parsed is not None and not error:
            if modo in ("criterios", "ce"):
                parsed_extra = dict(parsed)
            else:
                parsed_extra, error = validate_porcentajes_form(
                    criterios=crit_codes,
                    form_values=form_values,
                    prefix="pct_extra_",
                    etiqueta="extraordinaria",
                )
    mismos_pendiente = True
    parsed_pendiente = None
    if materia_puede_ser_pendiente(etapa_sel, curso):
        mismos_pendiente = str(form_values.get("mismos_pesos_pendiente") or "").strip() in (
            "1",
            "on",
            "true",
            "yes",
        )
        if not mismos_pendiente and parsed is not None and not error:
            if modo in ("criterios", "ce"):
                parsed_pendiente = dict(parsed)
            else:
                parsed_pendiente, error = validate_porcentajes_form(
                    criterios=crit_codes,
                    form_values=form_values,
                    prefix="pct_pendiente_",
                    etiqueta="pendiente",
                )
    base = (
        f"/competencias/materias/detalle"
        f"?etapa={etapa_sel}&curso={curso}&key={key}"
    )
    if error or parsed is None:
        from urllib.parse import quote

        return RedirectResponse(
            f"{base}&pd_error={quote(error or 'Error al guardar')}",
            status_code=303,
        )

    try:
        replace_porcentajes_materia(
            etapa=etapa_sel,
            curso_asignatura=curso,
            materia_key=key,
            porcentajes=parsed,
            updated_by=int(user["id"]) if user.get("id") is not None else None,
            modo_reparto=modo,
            mismos_pesos_extra=mismos_pesos,
            porcentajes_extra=parsed_extra,
            mismos_pesos_pendiente=mismos_pendiente,
            porcentajes_pendiente=parsed_pendiente,
        )
    except ValueError as exc:
        from urllib.parse import quote

        return RedirectResponse(
            f"{base}&pd_error={quote(str(exc) or 'Error al guardar')}",
            status_code=303,
        )
    _log_comp(
        user,
        "porcentajes_pd",
        entity="pd",
        detail=f"{etapa_sel} · curso {curso} · {key}",
    )
    return RedirectResponse(f"{base}&pd=saved", status_code=303)


@router.get("/catalogo-materias", include_in_schema=False)
def competencias_catalogo_materias_redirect(
    user: dict = Depends(load_user_dep),
    etapa: str | None = Query(None),
):
    """URL antigua → /competencias/materias."""
    _require_access(user, PERM_COMPETENCIAS_MATERIAS)
    qs = f"?etapa={etapa}" if (etapa or "").strip() else ""
    return RedirectResponse(f"/competencias/materias{qs}", status_code=303)


@router.get("/competencias-clave", response_class=HTMLResponse)
def competencias_clave(request: Request, user: dict = Depends(load_user_dep)):
    return _page(
        request,
        user=user,
        template="competencias/competencias_clave.html",
        title="Competencias · Evaluación de competencias",
        nav_section="competencias",
        competencias=list_competencias_clave(),
        saved=request.query_params.get("saved") == "1",
    )


@router.get("/competencias-clave/{abreviatura}", response_class=HTMLResponse)
def competencias_clave_edit(
    abreviatura: str,
    request: Request,
    user: dict = Depends(load_user_dep),
):
    competencia = get_competencia_clave(abreviatura)
    if not competencia:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    return _page(
        request,
        user=user,
        template="competencias/competencias_clave_edit.html",
        title=f"{competencia['abreviatura']} · Competencias",
        nav_section="competencias",
        competencia=competencia,
        error=None,
    )


@router.post("/competencias-clave/{abreviatura}", response_class=HTMLResponse)
async def competencias_clave_save(
    abreviatura: str,
    request: Request,
    user: dict = Depends(load_user_dep),
):
    _require_access(user, PERM_COMPETENCIAS_CLAVE)
    competencia = get_competencia_clave(abreviatura)
    if not competencia:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")

    form = await request.form()
    nombre = str(form.get("nombre") or "").strip()
    descriptores_eso = str(form.get("descriptores_eso") or "")
    descriptores_bach = str(form.get("descriptores_bach") or "")

    if not nombre:
        return _page(
            request,
            user=user,
            template="competencias/competencias_clave_edit.html",
            title=f"{competencia['abreviatura']} · Competencias",
            nav_section="competencias",
            competencia={
                **competencia,
                "nombre": nombre,
                "descriptores_eso": descriptores_eso,
                "descriptores_bach": descriptores_bach,
            },
            error="El nombre no puede estar vacío.",
        )

    update_competencia_clave(
        abreviatura=abreviatura,
        nombre=nombre,
        descriptores_eso=descriptores_eso,
        descriptores_bach=descriptores_bach,
    )
    _log_comp(
        user,
        "competencia_clave",
        entity="competencia_clave",
        detail=abreviatura,
    )
    return RedirectResponse(
        "/competencias/competencias-clave?saved=1", status_code=303
    )
