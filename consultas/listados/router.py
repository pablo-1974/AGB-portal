"""Rutas HTTP bajo ``/listados``."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from auth import load_user_dep
from ausencias.db import list_teachers_for_schedule_selector, list_teachers_min
from ausencias.services.pdf_schedule import (
    generate_multi_teacher_schedule_pdf_bytes,
    generate_schedule_pdf_with_title_bytes,
)
from config import settings
from context import ctx
from consultas.listados.pdf_list import (
    generate_multi_simple_table_pdf_bytes,
    generate_simple_table_pdf_bytes,
)
from consultas.listados.profes_queries import (
    list_distinct_profesor_departamentos,
    list_profesores_departamento_activos,
    list_profesorado_activos_con_cadena,
    list_profesorado_inicial_titulares,
    list_profesorado_sustitutos,
    list_profesorado_todos_con_estado,
    list_tutores_rows,
)
from consultas.listados.alumnos_queries import (
    LISTADO_ALUMNOS_EXTRA_COLUMNS,
    LISTADO_ALUMNOS_EXTRA_PARAM_NAMES,
    LISTADO_ALUMNOS_FILTROS,
    LISTADO_ALUMNOS_FILTRO_LEYENDAS,
    alumnos_listado_bundle,
    RESUMEN_ALUMNOS_FILTROS,
    build_matricula_resumenes,
    build_transporte_parada_resumen,
    normalize_alumnos_resumen_filtro,
    list_matricula_filter_cursos,
    list_matricula_filter_grupos,
    list_matricula_filter_paradas,
    normalize_alumnos_listado_filtro,
)
from consultas.listados.schedule_matrix import build_teacher_schedule_matrix, template_matrix_to_pdf_matrix
from consultas.listados.schedule_queries import (
    build_aggregate_matrix,
    build_guardias_matrix,
    fetch_all_guard_slots,
    fetch_class_slots_by_group,
    fetch_class_slots_by_room,
    fetch_guard_slots_by_type,
    list_distinct_class_groups_from_slots,
    list_distinct_class_rooms_from_slots,
    list_distinct_guard_types_from_slots,
    list_group_staff_for_pdf,
)
from consultas.listados.access import (
    can_access_alumnos,
    can_access_asignaturas,
    can_access_horarios,
    can_access_profesores,
    can_horarios_view,
    can_profesorado_tab,
    is_listados_staff,
    is_portal_role,
)
from consultas.listados.asignaturas_queries import (
    build_pendientes_resumenes,
    pendientes_resumen_titles,
)
from db.enrolled_subjects import (
    LISTADO_DISPLAY_COLUMNS,
    get_latest_import,
    list_distinct_curso_asignatura_options,
    list_enrolled_filter_alumnos,
    list_enrolled_filter_grupos,
    list_enrolled_filter_materias,
    list_enrolled_subject_rows,
)
from db.groups import list_distinct_cursos, list_group_names_for_curso
from utils.xlsx_export import simple_table_xlsx_bytes

router = APIRouter(prefix="/listados", tags=["listados"])
log = logging.getLogger(__name__)

LISTADOS_PDF_API = "bytes-v3"
LISTADOS_XLSX_API = "stdlib-zip"

__all__ = ["router", "LISTADOS_PDF_API", "LISTADOS_XLSX_API"]

_VIEWS = frozenset({"profesores", "grupos", "aulas", "guardias"})
_PROF_TABS = frozenset({"profesorado", "tutores", "departamentos", "grupos"})
_PROF_FILTERS = frozenset({"inicial", "activo", "sustituto", "todos"})
_ALUMNOS_TABS = frozenset({"resumen", "listados"})
_ASIGNATURAS_VISTAS = frozenset({"todas", "pendientes"})
_ASIGNATURAS_MODOS = frozenset({"resumen", "alumnos", "asignaturas"})

def _parse_alumnos_extra_cols(request: Request) -> frozenset[str]:
    return frozenset(
        k for k in LISTADO_ALUMNOS_EXTRA_PARAM_NAMES if k in request.query_params
    )


def _alumnos_extra_cols_query(extra_cols: frozenset[str]) -> str:
    if not extra_cols:
        return ""
    return "".join(f"&{name}=1" for name, _, _ in LISTADO_ALUMNOS_EXTRA_COLUMNS if name in extra_cols)


def _alumnos_listados_query_suffix(
    *,
    curso: str,
    grupo: str,
    parada: str,
    filtro: str,
    extra_cols: frozenset[str],
) -> str:
    parts: list[str] = []
    if curso:
        parts.append(f"curso={quote_plus(curso)}")
    if grupo:
        parts.append(f"grupo={quote_plus(grupo)}")
    if parada:
        parts.append(f"parada={quote_plus(parada)}")
    filtro = normalize_alumnos_listado_filtro(filtro)
    if filtro != "todos":
        parts.append(f"filtro={quote_plus(filtro)}")
    for name, _, _ in LISTADO_ALUMNOS_EXTRA_COLUMNS:
        if name in extra_cols:
            parts.append(f"{name}=1")
    return ("&" + "&".join(parts)) if parts else ""


def _alumnos_resumen_filtro_links(*, active_filtro: str) -> list[dict[str, str]]:
    active_filtro = normalize_alumnos_resumen_filtro(active_filtro)
    links: list[dict[str, str]] = []
    for fkey, flabel in RESUMEN_ALUMNOS_FILTROS:
        qs = f"&filtro={quote_plus(fkey)}" if fkey != "todos" else ""
        links.append(
            {
                "key": fkey,
                "label": flabel,
                "href": f"/listados/alumnos?tab=resumen{qs}",
                "active": fkey == active_filtro,
            }
        )
    return links


def _alumnos_listado_filtro_links(
    *,
    curso: str,
    grupo: str,
    parada: str,
    active_filtro: str,
    extra_cols: frozenset[str],
) -> list[dict[str, str]]:
    active_filtro = normalize_alumnos_listado_filtro(active_filtro)
    links: list[dict[str, str]] = []
    for fkey, flabel in LISTADO_ALUMNOS_FILTROS:
        qs = _alumnos_listados_query_suffix(
            curso=curso,
            grupo=grupo,
            parada=parada,
            filtro=fkey,
            extra_cols=extra_cols,
        )
        links.append(
            {
                "key": fkey,
                "label": flabel,
                "href": f"/listados/alumnos?tab=listados{qs}",
                "active": fkey == active_filtro,
            }
        )
    return links


def _safe_download_name(stem: str, *, ext: str) -> str:
    safe = re.sub(r"[^\w.\- ]+", "_", (stem or "").strip(), flags=re.UNICODE)
    safe = re.sub(r"\s+", "_", safe).strip("._") or "listado"
    return f"{safe[:72]}.{ext.lstrip('.')}"


def _pdf_response(data: bytes, filename: str) -> Response:
    if len(data) < 32:
        raise ValueError("PDF vacio")
    fn = _safe_download_name(filename, ext="pdf") if "." not in filename else filename
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


def _export_error(detail: str, exc: Exception) -> HTTPException:
    log.exception("%s: %s", detail, exc)
    return HTTPException(status_code=500, detail=f"{detail}: {exc}")


def _resolve_horarios_view(user: dict, raw: str | None) -> str:
    if raw is None or str(raw).strip() == "":
        return "grupos"
    v = _parse_view(str(raw).strip())
    if can_horarios_view(user, v):
        return v
    return "grupos"


def _default_prof_tab(user: dict) -> str:
    if can_profesorado_tab(user):
        return "profesorado"
    return "tutores"


def _resolve_prof_tab(user: dict, raw: str | None) -> str:
    if raw is None or str(raw).strip() == "":
        return _default_prof_tab(user)
    t = str(raw).strip().lower()
    if t not in _PROF_TABS:
        return _default_prof_tab(user)
    if t == "profesorado" and not can_profesorado_tab(user):
        return "tutores"
    if t == "profesorado":
        return "profesorado"
    if t in ("tutores", "departamentos", "grupos"):
        return t
    return "tutores"


def _prof_filter(raw: str | None) -> str | None:
    if raw is None or str(raw).strip() == "":
        return None
    f = str(raw).strip().lower()
    return f if f in _PROF_FILTERS else None


def _alumnos_tab(raw: str | None) -> str:
    t = (raw or "resumen").strip().lower()
    return t if t in _ALUMNOS_TABS else "resumen"


def _alumnos_tab_from_request(request: Request, tab_query: str | None) -> str:
    qp = request.query_params.get("tab")
    if qp is not None and str(qp).strip() != "":
        return _alumnos_tab(str(qp).strip())
    return _alumnos_tab(tab_query)


def _asignaturas_vista(raw: str | None) -> str:
    v = (raw or "todas").strip().lower()
    return v if v in _ASIGNATURAS_VISTAS else "todas"


def _asignaturas_vista_from_request(request: Request, vista_query: str | None) -> str:
    qp = request.query_params.get("vista")
    if qp is not None and str(qp).strip() != "":
        return _asignaturas_vista(str(qp).strip())
    return _asignaturas_vista(vista_query)


def _asignaturas_modo(raw: str | None, *, vista: str) -> str:
    if vista != "pendientes":
        return "alumnos"
    m = (raw or "resumen").strip().lower()
    if m == "desglose":
        m = "alumnos"
    return m if m in _ASIGNATURAS_MODOS else "alumnos"


def _parse_curso_asignatura_filter(raw: str | None) -> int | None:
    s = (raw or "").strip()
    if not s or not s.isdigit():
        return None
    return int(s)


def _asignaturas_modo_from_request(
    request: Request, modo_query: str | None, *, vista: str
) -> str:
    qp = request.query_params.get("modo")
    if qp is not None and str(qp).strip() != "":
        return _asignaturas_modo(str(qp).strip(), vista=vista)
    return _asignaturas_modo(modo_query, vista=vista)


def _asignaturas_list_url(
    vista: str,
    *,
    modo: str | None = None,
    curso: str | None = None,
    grupo: str | None = None,
    alumno: str | None = None,
    materia: str | None = None,
) -> str:
    from urllib.parse import urlencode

    q: dict[str, str] = {"vista": vista}
    if vista == "pendientes" and modo:
        q["modo"] = modo
    if curso:
        q["curso"] = curso
    if grupo:
        q["grupo"] = grupo
    if alumno:
        q["alumno"] = alumno
    if materia:
        q["materia"] = materia
    return "/listados/asignaturas?" + urlencode(q)


def _asignaturas_export_query_suffix(
    *,
    vista: str,
    modo: str,
    curso: str | None,
    grupo: str | None,
    alumno: str | None,
    materia: str | None,
) -> str:
    from urllib.parse import urlencode

    q: dict[str, str] = {"vista": vista}
    if vista == "pendientes":
        q["modo"] = modo
    if curso:
        q["curso"] = curso
    if grupo:
        q["grupo"] = grupo
    if alumno:
        q["alumno"] = alumno
    if materia:
        q["materia"] = materia
    return "&" + urlencode(q)


def _asignaturas_listado_bundle(
    *,
    vista: str,
    solo_pendientes: bool,
    filtro_por_asignatura: bool,
    curso: str | None,
    curso_asignatura: int | None,
    grupo: str | None,
    alumno: str | None,
    materia: str | None,
) -> tuple[list[tuple[str, str]], list[dict[str, Any]], str, bool]:
    if filtro_por_asignatura:
        rows = list_enrolled_subject_rows(
            curso_asignatura=curso_asignatura,
            grupo=grupo,
            alumno=alumno,
            materia=materia,
            solo_pendientes=solo_pendientes,
        )
    else:
        rows = list_enrolled_subject_rows(
            curso_grupos=curso,
            grupo=grupo,
            alumno=alumno,
            materia=materia,
            solo_pendientes=solo_pendientes,
        )
    can_export = bool(rows)
    parts: list[str] = []
    if solo_pendientes:
        parts.append("Pendientes")
    if curso:
        if filtro_por_asignatura:
            parts.append(f"Asignatura {curso}º")
        else:
            parts.append(curso)
    if grupo:
        parts.append(f"Grupo {grupo}")
    if alumno:
        parts.append(alumno)
    if materia:
        parts.append(materia)
    title = " — ".join(parts) if parts else "Asignaturas matriculadas"
    return (list(LISTADO_DISPLAY_COLUMNS), rows, title, can_export)


def _asignaturas_export_rows(
    rows: list[dict[str, Any]], columns: list[tuple[str, str]]
) -> list[list[str]]:
    keys = [key for _, key in columns]
    return [[str(r.get(k) or "") for k in keys] for r in rows]


def _pendientes_resumen_pdf_sections(
    pendientes_resumen: dict[str, dict[str, Any]],
    titles: dict[str, str],
) -> list[tuple[str, list[str], list[list[str]]]]:
    sections: list[tuple[str, list[str], list[list[str]]]] = []
    for key in ("eso", "bach", "fp"):
        resumen = pendientes_resumen.get(key) or {}
        columns = resumen.get("columns") or []
        rows_in = resumen.get("rows") or []
        if not columns:
            continue
        headers = ["Total", "Asignatura"] + [str(col["label"]) for col in columns]
        body: list[list[str]] = []
        for row in rows_in:
            body.append(
                [str(row.get("total") or 0), str(row.get("label") or "")]
                + [str(row.get("counts", {}).get(col["key"], 0)) for col in columns]
            )
        sections.append((f"Pendientes — {titles.get(key, key.upper())}", headers, body))
    return sections


def _pendientes_resumen_xlsx_rows(
    pendientes_resumen: dict[str, dict[str, Any]],
    titles: dict[str, str],
) -> tuple[list[str], list[list[object]]]:
    headers = ["Etapa", "Asignatura", "Columna", "Alumnos"]
    rows_out: list[list[object]] = []
    for key in ("eso", "bach", "fp"):
        resumen = pendientes_resumen.get(key) or {}
        etapa = titles.get(key, key.upper())
        for row in resumen.get("rows") or []:
            for col in resumen.get("columns") or []:
                rows_out.append(
                    [
                        etapa,
                        row.get("label") or "",
                        col.get("label") or "",
                        row.get("counts", {}).get(col["key"], 0),
                    ]
                )
    return headers, rows_out


def _prof_tab_from_request(request: Request, tab_query: str | None, user: dict) -> str:
    qp = request.query_params.get("tab")
    if qp is not None and str(qp).strip() != "":
        return _resolve_prof_tab(user, str(qp).strip())
    return _resolve_prof_tab(user, tab_query)


def _profesores_bundle(
    *,
    tab: str,
    pf: str | None,
    dept: str | None,
    group: str | None = None,
) -> tuple[list[str], list[dict], str, bool]:
    if tab == "tutores":
        rows = list_tutores_rows()
        return (["Grupo", "Nombre", "Email"], rows, "Tutores", True)
    if tab == "grupos":
        g = (group or "").strip()
        if not g:
            return (["Nombre", "Asignatura"], [], "Por grupos", False)
        staff = list_group_staff_for_pdf(g)
        rows = [
            {"name": s["nombre"], "asignatura": s["asignatura"]}
            for s in staff
        ]
        return (["Nombre", "Asignatura"], rows, f"Profesorado del grupo - {g}", True)
    if tab == "departamentos":
        d = (dept or "").strip()
        if not d:
            return (["Nombre", "Email"], [], "Departamentos", False)
        rows = list_profesores_departamento_activos(d)
        return (["Nombre", "Email"], rows, f"Departamento - {d}", True)
    if not pf:
        return (["Nombre", "Email"], [], "Profesorado", False)
    if pf == "inicial":
        rows = list_profesorado_inicial_titulares()
        title = "Profesorado - Inicial (titular)"
    elif pf == "activo":
        rows = list_profesorado_activos_con_cadena()
        title = "Profesorado - Activo"
    elif pf == "sustituto":
        rows = list_profesorado_sustitutos()
        title = "Profesorado - Sustituto"
    elif pf == "todos":
        rows = list_profesorado_todos_con_estado()
        title = "Profesorado - Todos"
    else:
        rows = []
        title = "Profesorado"
    return (["Nombre", "Email"], rows, title, True)


def _parse_view(raw: str | None) -> str:
    if raw is None:
        return "profesores"
    if not isinstance(raw, str):
        raw = str(raw)
    v = raw.strip().lower()
    return v if v in _VIEWS else "profesores"


def _view_from_request(request: Request, view_query: str | None, user: dict) -> str:
    qp = request.query_params.get("view")
    if qp is not None and str(qp).strip() != "":
        return _resolve_horarios_view(user, str(qp).strip())
    return _resolve_horarios_view(user, view_query)


@router.get("/", response_class=HTMLResponse)
def listados_hub(request: Request, user: dict = Depends(load_user_dep)):
    if not is_portal_role(user):
        raise HTTPException(status_code=403, detail="No tienes permiso para acceder a Listados.")
    return request.app.state.templates.TemplateResponse(
        "listados/hub_all.html",
        ctx(
            request,
            user=user,
            title="Listados",
            is_listados_staff=is_listados_staff(user),
            can_access_asignaturas=can_access_asignaturas(user),
        ),
    )


@router.get("/asignaturas", response_class=HTMLResponse)
def listados_asignaturas(
    request: Request,
    user: dict = Depends(load_user_dep),
    vista: str | None = Query(default=None),
    modo: str | None = Query(default=None),
    curso: str | None = Query(default=None),
    grupo: str | None = Query(default=None),
    alumno: str | None = Query(default=None),
    materia: str | None = Query(default=None),
):
    if not can_access_asignaturas(user):
        raise HTTPException(status_code=403, detail="No tienes permiso para consultar asignaturas matriculadas.")
    selected_vista = _asignaturas_vista_from_request(request, vista)
    selected_modo = _asignaturas_modo_from_request(request, modo, vista=selected_vista)
    solo_pendientes = selected_vista == "pendientes"
    show_resumen = solo_pendientes and selected_modo == "resumen"
    filtro_por_asignatura = (
        selected_vista == "pendientes" and selected_modo == "asignaturas"
    )
    selected_curso = (curso or "").strip() or None
    selected_curso_asignatura = (
        _parse_curso_asignatura_filter(selected_curso) if filtro_por_asignatura else None
    )
    selected_grupo = (grupo or "").strip() or None
    selected_alumno = (alumno or "").strip() or None
    selected_materia = (materia or "").strip() or None
    latest = get_latest_import()
    url_kw = dict(
        curso=selected_curso,
        grupo=selected_grupo,
        alumno=selected_alumno,
        materia=selected_materia,
    )
    pendientes_resumen = build_pendientes_resumenes() if show_resumen else None
    resumen_titles = pendientes_resumen_titles()
    if show_resumen:
        preview_rows = []
        table_columns = list(LISTADO_DISPLAY_COLUMNS)
        export_title = "Pendientes — Resumen"
        can_export = bool(
            pendientes_resumen
            and any(
                (pendientes_resumen.get(key) or {}).get("rows")
                for key in ("eso", "bach", "fp")
            )
        )
    else:
        table_columns, preview_rows, export_title, can_export = _asignaturas_listado_bundle(
            vista=selected_vista,
            solo_pendientes=solo_pendientes,
            filtro_por_asignatura=filtro_por_asignatura,
            curso=selected_curso,
            curso_asignatura=selected_curso_asignatura,
            grupo=selected_grupo,
            alumno=selected_alumno,
            materia=selected_materia,
        )
    curso_requerido = bool(selected_curso or selected_curso_asignatura)
    if filtro_por_asignatura:
        filter_curso_options = list_distinct_curso_asignatura_options(
            solo_pendientes=solo_pendientes
        )
        filter_grupos = (
            list_enrolled_filter_grupos(
                curso_asignatura=selected_curso_asignatura,
                solo_pendientes=solo_pendientes,
            )
            if curso_requerido
            else []
        )
        filter_alumnos = (
            list_enrolled_filter_alumnos(
                curso_asignatura=selected_curso_asignatura,
                grupo=selected_grupo,
                solo_pendientes=solo_pendientes,
            )
            if curso_requerido
            else []
        )
        filter_materias = (
            list_enrolled_filter_materias(
                curso_asignatura=selected_curso_asignatura,
                grupo=selected_grupo,
                alumno=selected_alumno,
                solo_pendientes=solo_pendientes,
            )
            if curso_requerido
            else []
        )
    else:
        filter_curso_options = [
            {"value": c, "label": c} for c in list_distinct_cursos()
        ]
        filter_grupos = (
            list_group_names_for_curso(selected_curso) if selected_curso else []
        )
        filter_alumnos = (
            list_enrolled_filter_alumnos(
                curso_grupos=selected_curso,
                grupo=selected_grupo,
                solo_pendientes=solo_pendientes,
            )
            if selected_curso
            else []
        )
        filter_materias = (
            list_enrolled_filter_materias(
                curso_grupos=selected_curso,
                grupo=selected_grupo,
                alumno=selected_alumno,
                solo_pendientes=solo_pendientes,
            )
            if selected_curso
            else []
        )
    export_query_suffix = _asignaturas_export_query_suffix(
        vista=selected_vista,
        modo=selected_modo,
        curso=selected_curso,
        grupo=selected_grupo,
        alumno=selected_alumno,
        materia=selected_materia,
    )
    export_qs = export_query_suffix.lstrip("&")
    export_pdf_url = f"/listados/asignaturas/export.pdf?{export_qs}"
    export_xlsx_url = f"/listados/asignaturas/export.xlsx?{export_qs}"
    return request.app.state.templates.TemplateResponse(
        "listados/asignaturas.html",
        ctx(
            request,
            user=user,
            title="Asignaturas matriculadas",
            vista=selected_vista,
            modo=selected_modo,
            filtro_por_asignatura=filtro_por_asignatura,
            url_todas=_asignaturas_list_url("todas", **url_kw),
            url_pendientes=_asignaturas_list_url("pendientes", modo="resumen"),
            url_resumen=_asignaturas_list_url("pendientes", modo="resumen"),
            url_alumnos=_asignaturas_list_url("pendientes", modo="alumnos"),
            url_asignaturas=_asignaturas_list_url("pendientes", modo="asignaturas"),
            latest_import=latest,
            preview_rows=preview_rows,
            pendientes_resumen=pendientes_resumen,
            pendientes_resumen_titles=resumen_titles,
            table_columns=table_columns,
            filter_curso_options=filter_curso_options,
            filter_grupos=filter_grupos,
            filter_alumnos=filter_alumnos,
            filter_materias=filter_materias,
            selected_curso=selected_curso,
            selected_grupo=selected_grupo,
            selected_alumno=selected_alumno,
            selected_materia=selected_materia,
            can_export=can_export,
            export_query_suffix=export_query_suffix,
            export_pdf_url=export_pdf_url,
            export_xlsx_url=export_xlsx_url,
            export_title=export_title,
        ),
    )


@router.get("/asignaturas/export.pdf")
def listados_asignaturas_export_pdf(
    request: Request,
    user: dict = Depends(load_user_dep),
    vista: str | None = Query(default=None),
    modo: str | None = Query(default=None),
    curso: str | None = None,
    grupo: str | None = None,
    alumno: str | None = None,
    materia: str | None = None,
):
    if not can_access_asignaturas(user):
        raise HTTPException(
            status_code=403,
            detail="No tienes permiso para exportar asignaturas matriculadas.",
        )
    selected_vista = _asignaturas_vista_from_request(request, vista)
    selected_modo = _asignaturas_modo_from_request(request, modo, vista=selected_vista)
    show_resumen = selected_vista == "pendientes" and selected_modo == "resumen"
    filtro_por_asignatura = (
        selected_vista == "pendientes" and selected_modo == "asignaturas"
    )
    selected_curso = (curso or "").strip() or None
    selected_curso_asignatura = (
        _parse_curso_asignatura_filter(selected_curso) if filtro_por_asignatura else None
    )
    center = settings.INSTITUTION_NAME or "IES"
    try:
        if show_resumen:
            pendientes_resumen = build_pendientes_resumenes()
            titles = pendientes_resumen_titles()
            sections = _pendientes_resumen_pdf_sections(pendientes_resumen, titles)
            if not sections:
                raise HTTPException(status_code=400, detail="No hay datos de resumen para exportar.")
            pdf_data = generate_multi_simple_table_pdf_bytes(
                center_name=center,
                sections=[
                    (f"Listados - {headline}", headers, rows)
                    for headline, headers, rows in sections
                ],
            )
            return _pdf_response(pdf_data, "pendientes_resumen.pdf")
        table_columns, rows, export_title, can_export = _asignaturas_listado_bundle(
            vista=selected_vista,
            solo_pendientes=selected_vista == "pendientes",
            filtro_por_asignatura=filtro_por_asignatura,
            curso=selected_curso,
            curso_asignatura=selected_curso_asignatura,
            grupo=(grupo or "").strip() or None,
            alumno=(alumno or "").strip() or None,
            materia=(materia or "").strip() or None,
        )
        if not can_export:
            raise HTTPException(
                status_code=400,
                detail="No hay datos para exportar.",
            )
        headers = [label for label, _ in table_columns]
        pdf_data = generate_simple_table_pdf_bytes(
            center_name=center,
            headline=f"Listados - Asignaturas - {export_title}",
            headers=headers,
            rows=_asignaturas_export_rows(rows, table_columns),
        )
        return _pdf_response(pdf_data, _safe_download_name(export_title, ext="pdf"))
    except HTTPException:
        raise
    except Exception as exc:
        raise _export_error("Error al generar PDF de asignaturas", exc) from exc


@router.get("/asignaturas/export.xlsx")
def listados_asignaturas_export_xlsx(
    request: Request,
    user: dict = Depends(load_user_dep),
    vista: str | None = Query(default=None),
    modo: str | None = Query(default=None),
    curso: str | None = None,
    grupo: str | None = None,
    alumno: str | None = None,
    materia: str | None = None,
):
    if not can_access_asignaturas(user):
        raise HTTPException(
            status_code=403,
            detail="No tienes permiso para exportar asignaturas matriculadas.",
        )
    selected_vista = _asignaturas_vista_from_request(request, vista)
    selected_modo = _asignaturas_modo_from_request(request, modo, vista=selected_vista)
    show_resumen = selected_vista == "pendientes" and selected_modo == "resumen"
    filtro_por_asignatura = (
        selected_vista == "pendientes" and selected_modo == "asignaturas"
    )
    selected_curso = (curso or "").strip() or None
    selected_curso_asignatura = (
        _parse_curso_asignatura_filter(selected_curso) if filtro_por_asignatura else None
    )
    try:
        if show_resumen:
            pendientes_resumen = build_pendientes_resumenes()
            titles = pendientes_resumen_titles()
            headers, rows = _pendientes_resumen_xlsx_rows(pendientes_resumen, titles)
            if not rows:
                raise HTTPException(status_code=400, detail="No hay datos de resumen para exportar.")
            xlsx_data = simple_table_xlsx_bytes(
                sheet_name="Pendientes",
                headers=headers,
                rows=rows,
            )
            return Response(
                xlsx_data,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={
                    "Content-Disposition": 'attachment; filename="pendientes_resumen.xlsx"',
                },
            )
        table_columns, rows, export_title, can_export = _asignaturas_listado_bundle(
            vista=selected_vista,
            solo_pendientes=selected_vista == "pendientes",
            filtro_por_asignatura=filtro_por_asignatura,
            curso=selected_curso,
            curso_asignatura=selected_curso_asignatura,
            grupo=(grupo or "").strip() or None,
            alumno=(alumno or "").strip() or None,
            materia=(materia or "").strip() or None,
        )
        if not can_export:
            raise HTTPException(
                status_code=400,
                detail="No hay datos para exportar.",
            )
        headers = [label for label, _ in table_columns]
        xlsx_data = simple_table_xlsx_bytes(
            sheet_name="Asignaturas",
            headers=headers,
            rows=_asignaturas_export_rows(rows, table_columns),
        )
        return Response(
            xlsx_data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{_safe_download_name(export_title, ext="xlsx")}"',
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _export_error("Error al generar Excel de asignaturas", exc) from exc


@router.get("/profesores", response_class=HTMLResponse)
def listados_profesores(
    request: Request,
    user: dict = Depends(load_user_dep),
    tab: str | None = Query(default=None),
    pf: str | None = Query(default=None),
    dept: str | None = Query(default=None),
    group: str | None = Query(default=None),
):
    if not can_access_profesores(user):
        raise HTTPException(status_code=403, detail="No tienes permiso para consultar el listado de profesorado.")
    t = _prof_tab_from_request(request, tab, user)
    filt = _prof_filter(pf)
    d = (dept or "").strip() or None
    g = (group or "").strip() or None
    headers, rows, pdf_title, can_pdf = _profesores_bundle(tab=t, pf=filt, dept=d, group=g)
    departments = list_distinct_profesor_departamentos()
    groups = list_distinct_class_groups_from_slots()
    return request.app.state.templates.TemplateResponse(
        "listados/profesores.html",
        ctx(
            request,
            user=user,
            title="Listados - Profesorado",
            tab=t,
            selected_pf=filt or "",
            selected_dept=d or "",
            selected_group=g or "",
            table_headers=headers,
            table_rows=rows,
            pdf_title=pdf_title,
            can_export_pdf=can_pdf,
            departments_options=departments,
            groups_options=groups,
            can_profesorado_tab=can_profesorado_tab(user),
        ),
    )


def _profesores_grupos_pdf_rows(staff: list[dict]) -> list[list[str]]:
    return [
        [str(r.get("name") or ""), str(r.get("asignatura") or "")]
        for r in staff
    ]


@router.get("/profesores/export.pdf")
def listados_profesores_export_pdf(
    request: Request,
    user: dict = Depends(load_user_dep),
    tab: str | None = Query(default=None),
    pf: str | None = Query(default=None),
    dept: str | None = Query(default=None),
    group: str | None = Query(default=None),
    all_: int | None = Query(default=None, alias="all"),
):
    if not can_access_profesores(user):
        raise HTTPException(status_code=403, detail="No tienes permiso para consultar el listado de profesorado.")
    t = _prof_tab_from_request(request, tab, user)
    filt = _prof_filter(pf)
    d = (dept or "").strip() or None
    g = (group or "").strip() or None
    try:
        center = settings.INSTITUTION_NAME or "IES"
        if t == "grupos":
            headers = ["Nombre", "Asignatura"]
            if all_ == 1:
                sections: list[tuple[str, list[str], list[list[str]]]] = []
                for gname in list_distinct_class_groups_from_slots():
                    _, rows, title, _ = _profesores_bundle(tab="grupos", pf=None, dept=None, group=gname)
                    sections.append(
                        (
                            f"Listados - {title}",
                            headers,
                            _profesores_grupos_pdf_rows(rows),
                        )
                    )
                if not sections:
                    raise HTTPException(status_code=404, detail="No hay grupos para exportar.")
                pdf_data = generate_multi_simple_table_pdf_bytes(
                    center_name=center,
                    sections=sections,
                )
                return _pdf_response(pdf_data, "profesorado_todos_grupos.pdf")
            headers, rows, pdf_title, can_pdf = _profesores_bundle(
                tab=t, pf=filt, dept=d, group=g
            )
            if not can_pdf:
                raise HTTPException(status_code=400, detail="Selecciona un grupo para exportar.")
            pdf_data = generate_simple_table_pdf_bytes(
                center_name=center,
                headline=f"Listados - {pdf_title}",
                headers=headers,
                rows=_profesores_grupos_pdf_rows(rows),
            )
            return _pdf_response(pdf_data, _safe_download_name(pdf_title, ext="pdf"))

        headers, rows, pdf_title, can_pdf = _profesores_bundle(tab=t, pf=filt, dept=d, group=g)
        if not can_pdf:
            raise HTTPException(status_code=400, detail="Selecciona criterio de profesorado o un departamento para exportar.")
        pdf_rows: list[list[str]] = []
        for r in rows:
            if t == "tutores":
                pdf_rows.append([str(r.get("grupo") or ""), str(r.get("name") or ""), str(r.get("email") or "")])
            else:
                pdf_rows.append([str(r.get("name") or ""), str(r.get("email") or "")])
        pdf_data = generate_simple_table_pdf_bytes(
            center_name=center,
            headline=f"Listados - {pdf_title}",
            headers=headers,
            rows=pdf_rows,
        )
        return _pdf_response(pdf_data, _safe_download_name(pdf_title, ext="pdf"))
    except HTTPException:
        raise
    except Exception as exc:
        raise _export_error("Error al generar PDF de profesorado", exc) from exc


@router.get("/alumnos", response_class=HTMLResponse)
def listados_alumnos(
    request: Request,
    user: dict = Depends(load_user_dep),
    tab: str | None = Query(default=None),
    curso: str | None = None,
    grupo: str | None = None,
    parada: str | None = None,
):
    if not can_access_alumnos(user):
        raise HTTPException(status_code=403, detail="No tienes permiso para consultar el listado de alumnos.")
    t = _alumnos_tab_from_request(request, tab)
    selected_curso = (curso or "").strip() or None
    selected_grupo = (grupo or "").strip() or None
    selected_parada = (parada or "").strip() or None
    extra_cols = _parse_alumnos_extra_cols(request)
    listado_filtro = normalize_alumnos_listado_filtro(request.query_params.get("filtro"))
    if listado_filtro != "transporte":
        selected_parada = None
    resumen_filtro = normalize_alumnos_resumen_filtro(request.query_params.get("filtro"))
    if t == "resumen":
        matricula_resumenes = (
            None
            if resumen_filtro == "transporte"
            else build_matricula_resumenes(filtro=resumen_filtro)
        )
        transporte_resumen = (
            build_transporte_parada_resumen() if resumen_filtro == "transporte" else None
        )
    else:
        matricula_resumenes = None
        transporte_resumen = None
    listados_qs = _alumnos_listados_query_suffix(
        curso=selected_curso or "",
        grupo=selected_grupo or "",
        parada=selected_parada or "",
        filtro=listado_filtro,
        extra_cols=extra_cols,
    )
    table_columns, rows, export_title, can_export = alumnos_listado_bundle(
        curso=selected_curso,
        grupo=selected_grupo,
        parada=selected_parada,
        extra_cols=extra_cols,
        filtro=listado_filtro,
    )
    return request.app.state.templates.TemplateResponse(
        "listados/alumnos.html",
        ctx(
            request,
            user=user,
            title="Listados - Alumnos",
            tab=t,
            matricula_resumenes=matricula_resumenes,
            transporte_resumen=transporte_resumen,
            resumen_filtro=resumen_filtro,
            resumen_filtro_links=_alumnos_resumen_filtro_links(active_filtro=resumen_filtro),
            table_columns=table_columns,
            table_rows=rows,
            export_title=export_title,
            can_export=can_export,
            filter_cursos=list_matricula_filter_cursos(),
            filter_grupos=list_matricula_filter_grupos(curso=selected_curso),
            filter_paradas=(
                list_matricula_filter_paradas(curso=selected_curso, grupo=selected_grupo)
                if listado_filtro == "transporte"
                else []
            ),
            selected_curso=selected_curso or "",
            selected_grupo=selected_grupo or "",
            selected_parada=selected_parada or "",
            extra_column_options=LISTADO_ALUMNOS_EXTRA_COLUMNS,
            active_extra_cols=extra_cols,
            listado_filtro=listado_filtro,
            listado_filtro_links=_alumnos_listado_filtro_links(
                curso=selected_curso or "",
                grupo=selected_grupo or "",
                parada=selected_parada or "",
                active_filtro=listado_filtro,
                extra_cols=extra_cols,
            ),
            listados_query_suffix=listados_qs,
            export_query_suffix=listados_qs,
            filtro_leyenda=LISTADO_ALUMNOS_FILTRO_LEYENDAS.get(listado_filtro, ""),
        ),
    )


def _alumnos_export_rows(rows: list[dict], columns: list[tuple[str, str]]) -> list[list[str]]:
    keys = [key for _, key in columns]
    return [[str(r.get(k) or "") for k in keys] for r in rows]


@router.get("/alumnos/export.pdf")
def listados_alumnos_export_pdf(
    request: Request,
    user: dict = Depends(load_user_dep),
    curso: str | None = None,
    grupo: str | None = None,
    parada: str | None = None,
):
    if not can_access_alumnos(user):
        raise HTTPException(status_code=403, detail="No tienes permiso para exportar el listado de alumnos.")
    selected_curso = (curso or "").strip() or None
    selected_grupo = (grupo or "").strip() or None
    selected_parada = (parada or "").strip() or None
    extra_cols = _parse_alumnos_extra_cols(request)
    listado_filtro = normalize_alumnos_listado_filtro(request.query_params.get("filtro"))
    if listado_filtro != "transporte":
        selected_parada = None
    table_columns, rows, export_title, can_export = alumnos_listado_bundle(
        curso=selected_curso,
        grupo=selected_grupo,
        parada=selected_parada,
        extra_cols=extra_cols,
        filtro=listado_filtro,
    )
    if not can_export:
        raise HTTPException(
            status_code=400,
            detail="Selecciona un curso, un grupo o una parada para exportar.",
        )
    try:
        center = settings.INSTITUTION_NAME or "IES"
        headers = [label for label, _ in table_columns]
        pdf_data = generate_simple_table_pdf_bytes(
            center_name=center,
            headline=f"Listados - Alumnos - {export_title}",
            headers=headers,
            rows=_alumnos_export_rows(rows, table_columns),
        )
        return _pdf_response(pdf_data, _safe_download_name(export_title, ext="pdf"))
    except HTTPException:
        raise
    except Exception as exc:
        raise _export_error("Error al generar PDF de alumnos", exc) from exc


@router.get("/alumnos/export.xlsx")
def listados_alumnos_export_xlsx(
    request: Request,
    user: dict = Depends(load_user_dep),
    curso: str | None = None,
    grupo: str | None = None,
    parada: str | None = None,
):
    if not can_access_alumnos(user):
        raise HTTPException(status_code=403, detail="No tienes permiso para exportar el listado de alumnos.")
    selected_curso = (curso or "").strip() or None
    selected_grupo = (grupo or "").strip() or None
    selected_parada = (parada or "").strip() or None
    extra_cols = _parse_alumnos_extra_cols(request)
    listado_filtro = normalize_alumnos_listado_filtro(request.query_params.get("filtro"))
    if listado_filtro != "transporte":
        selected_parada = None
    table_columns, rows, export_title, can_export = alumnos_listado_bundle(
        curso=selected_curso,
        grupo=selected_grupo,
        parada=selected_parada,
        extra_cols=extra_cols,
        filtro=listado_filtro,
    )
    if not can_export:
        raise HTTPException(
            status_code=400,
            detail="Selecciona un curso, un grupo o una parada para exportar.",
        )
    try:
        headers = [label for label, _ in table_columns]
        xlsx_data = simple_table_xlsx_bytes(
            sheet_name="Alumnos",
            headers=headers,
            rows=_alumnos_export_rows(rows, table_columns),
        )
        return Response(
            xlsx_data,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{_safe_download_name(export_title, ext="xlsx")}"',
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _export_error("Error al generar Excel de alumnos", exc) from exc


def _matrix_for_view(
    *,
    view: str,
    teacher_id: int | None,
    group: str | None,
    room: str | None,
    guard_type: str | None,
) -> tuple[list[list[Any]], bool]:
    show = False
    matrix: list[list[Any]] = [[None for _ in range(5)] for _ in range(7)]
    if view == "profesores" and teacher_id is not None:
        matrix = build_teacher_schedule_matrix(teacher_id=teacher_id)
        show = True
    elif view == "grupos" and (group or "").strip():
        rows = fetch_class_slots_by_group(group or "")
        matrix = build_aggregate_matrix(rows, mode="group")
        show = True
    elif view == "aulas" and (room or "").strip():
        rows = fetch_class_slots_by_room(room or "")
        matrix = build_aggregate_matrix(rows, mode="room")
        show = True
    elif view == "guardias":
        if (guard_type or "").strip():
            rows = fetch_guard_slots_by_type(guard_type or "")
            matrix = build_aggregate_matrix(rows, mode="guard")
        else:
            rows = fetch_all_guard_slots()
            matrix = build_guardias_matrix(rows)
        show = True
    return matrix, show


def _pdf_headline(
    *,
    view: str,
    teacher_name: str,
    group: str | None,
    room: str | None,
    guard_type: str | None,
) -> str:
    if view == "profesores":
        return (teacher_name or "").strip() or "Profesor"
    if view == "grupos" and group:
        return f"Horario del grupo - {group}"
    if view == "aulas" and room:
        return f"Horario del aula - {room}"
    if view == "guardias":
        if guard_type:
            return f"Distribucion guardias - {guard_type}"
        return "Distribucion de guardias (todas)"
    return "Horario"


def _include_group_staff_flag(include_staff: int | None) -> bool:
    return include_staff == 1


@router.get("/horarios/export.pdf")
def listados_horarios_export_pdf(
    request: Request,
    user: dict = Depends(load_user_dep),
    all_: int | None = Query(default=None, alias="all"),
    view: str | None = Query(default=None),
    teacher_id: int | None = Query(default=None),
    group: str | None = Query(default=None),
    room: str | None = Query(default=None),
    guard_type: str | None = Query(default=None),
    include_staff: int | None = Query(default=None),
):
    if not can_access_horarios(user):
        raise HTTPException(status_code=403, detail="No tienes permiso para consultar horarios.")
    try:
        return _horarios_export_pdf_impl(
            request=request,
            user=user,
            all_=all_,
            view=view,
            teacher_id=teacher_id,
            group=group,
            room=room,
            guard_type=guard_type,
            include_staff=include_staff,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _export_error("Error al generar PDF de horarios", exc) from exc


def _horarios_export_pdf_impl(
    *,
    request: Request,
    user: dict,
    all_: int | None,
    view: str | None,
    teacher_id: int | None,
    group: str | None,
    room: str | None,
    guard_type: str | None,
    include_staff: int | None,
):
    center = settings.INSTITUTION_NAME or "IES"
    v = _view_from_request(request, view, user)
    if not can_horarios_view(user, v):
        raise HTTPException(status_code=403, detail="No tienes permiso para esta vista de horarios.")
    with_group_staff = v == "grupos" and _include_group_staff_flag(include_staff)
    if all_ == 1:
        sections: list[tuple[str, list] | tuple[str, list, list[dict] | None]] = []
        out_name = "horarios_export.pdf"
        if v == "profesores":
            out_name = "horarios_todos_profesores_activos.pdf"
            for t in list_teachers_min():
                tid = int(t["id"])
                name = str(t.get("name") or t.get("alias") or "").strip() or f"Profesor {tid}"
                tm = build_teacher_schedule_matrix(teacher_id=tid)
                if all(c is None for row in tm for c in row):
                    continue
                sections.append((name, template_matrix_to_pdf_matrix(tm)))
        elif v == "grupos":
            out_name = "horarios_todos_grupos.pdf"
            for gname in list_distinct_class_groups_from_slots():
                rows = fetch_class_slots_by_group(gname)
                tm = build_aggregate_matrix(rows, mode="group")
                if all(c is None for row in tm for c in row):
                    continue
                staff = list_group_staff_for_pdf(gname) if with_group_staff else None
                sections.append(
                    (
                        _pdf_headline(view="grupos", teacher_name="", group=gname, room=None, guard_type=None),
                        template_matrix_to_pdf_matrix(tm),
                        staff,
                    )
                )
        elif v == "aulas":
            out_name = "horarios_todas_aulas.pdf"
            for rname in list_distinct_class_rooms_from_slots():
                rows = fetch_class_slots_by_room(rname)
                tm = build_aggregate_matrix(rows, mode="room")
                if all(c is None for row in tm for c in row):
                    continue
                sections.append(
                    (
                        _pdf_headline(view="aulas", teacher_name="", group=None, room=rname, guard_type=None),
                        template_matrix_to_pdf_matrix(tm),
                    )
                )
        else:
            raise HTTPException(status_code=400, detail="La exportacion masiva no esta disponible para esta vista.")
        if not sections:
            raise HTTPException(status_code=404, detail="No hay horarios para exportar.")
        return _pdf_response(generate_multi_teacher_schedule_pdf_bytes(center, sections), out_name)
    g = (group or "").strip() or None
    r = (room or "").strip() or None
    gt = (guard_type or "").strip() or None
    matrix, ok = _matrix_for_view(view=v, teacher_id=teacher_id, group=g, room=r, guard_type=gt)
    if not ok:
        raise HTTPException(status_code=400, detail="Selecciona profesor, grupo, aula o tipo de guardia.")
    pdf_m = template_matrix_to_pdf_matrix(matrix)
    tname = ""
    if v == "profesores" and teacher_id is not None:
        trow = next((x for x in list_teachers_for_schedule_selector() if int(x["id"]) == int(teacher_id)), None)
        tname = str(trow.get("name") or "").strip() if trow else f"Profesor {teacher_id}"
    headline = _pdf_headline(view=v, teacher_name=tname, group=g, room=r, guard_type=gt)
    group_staff = list_group_staff_for_pdf(g) if with_group_staff and g else None
    pdf_data = generate_schedule_pdf_with_title_bytes(
        center,
        headline,
        pdf_m,
        guardias_recreo_split_labels=v == "guardias" and not gt,
        group_staff=group_staff,
    )
    return _pdf_response(pdf_data, _safe_download_name(headline, ext="pdf"))


@router.get("/horarios", response_class=HTMLResponse)
def listados_horarios(
    request: Request,
    user: dict = Depends(load_user_dep),
    view: str | None = Query(default=None),
    teacher_id: int | None = Query(default=None),
    group: str | None = Query(default=None),
    room: str | None = Query(default=None),
    guard_type: str | None = Query(default=None),
):
    if not can_access_horarios(user):
        raise HTTPException(status_code=403, detail="No tienes permiso para consultar horarios.")
    v = _view_from_request(request, view, user)
    g = (group or "").strip() or None
    r = (room or "").strip() or None
    gt = (guard_type or "").strip() or None
    matrix, show_schedule = _matrix_for_view(
        view=v, teacher_id=teacher_id, group=g, room=r, guard_type=gt
    )
    return request.app.state.templates.TemplateResponse(
        "listados/horarios.html",
        ctx(
            request,
            user=user,
            title="Listados - Horarios",
            view=v,
            can_horarios_profesores=can_horarios_view(user, "profesores"),
            can_horarios_grupos=can_horarios_view(user, "grupos"),
            can_horarios_aulas=can_horarios_view(user, "aulas"),
            can_horarios_guardias=can_horarios_view(user, "guardias"),
            teachers=list_teachers_for_schedule_selector(),
            groups_options=list_distinct_class_groups_from_slots(),
            rooms_options=list_distinct_class_rooms_from_slots(),
            guards_options=list_distinct_guard_types_from_slots(),
            selected_teacher_id=teacher_id,
            selected_group=g or "",
            selected_room=r or "",
            selected_guard_type=gt or "",
            schedule=matrix,
            show_schedule=show_schedule,
        ),
    )
