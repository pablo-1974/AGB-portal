# routers/incidents_list.py
"""
Listado de incidencias.
Vista común con filtros automáticos y permisos por rol.
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from datetime import date

from auth import load_user_dep
from context import ctx

from db.incidents import get_incidents
from db.school_calendar import get_course_start_iso
from db.students import get_all_groups, get_students_by_group
from db.users import get_all_teachers

from utils.permissions import has_permission
from utils.enums import (
    PERM_LISTAR_INCIDENCIAS,
    PERM_EDITAR_INCIDENCIA,
    ROLE_ADMIN,
    ROLE_CONVIVENCIA,
    ROLE_DIRECTOR,
    ROLE_JEFE,
    ROLE_SECRETARIO,
    ROLE_EXTRAESCOLARES,
    ROLE_ORIENTADOR,
    ROLE_PROFESOR,
)

router = APIRouter()

ROLES_VEN_TODAS = {
    ROLE_ADMIN,
    ROLE_CONVIVENCIA,
    ROLE_DIRECTOR,
    ROLE_JEFE,
    ROLE_SECRETARIO,
}

ROLES_VEN_PROPIAS = {
    ROLE_ORIENTADOR,
    ROLE_PROFESOR,
    ROLE_EXTRAESCOLARES,
}


def _base_filters(request: Request) -> tuple[str, str, str | None, str | None, str | None, int | None]:
    qp = request.query_params
    fecha_desde = qp.get("fecha_desde") or get_course_start_iso()
    fecha_hasta = qp.get("fecha_hasta") or date.today().isoformat()
    grupo = qp.get("grupo") or None
    alumno = qp.get("alumno") or None
    gravedad = qp.get("gravedad") or None
    profesor_id_raw = qp.get("profesor_id")
    profesor_id = int(profesor_id_raw) if (profesor_id_raw and profesor_id_raw.isdigit()) else None
    return fecha_desde, fecha_hasta, grupo, alumno, gravedad, profesor_id


@router.get("/incidents/list", response_class=HTMLResponse)
def incidents_list(request: Request, user: dict = Depends(load_user_dep)):
    if not has_permission(user, PERM_LISTAR_INCIDENCIAS):
        raise HTTPException(status_code=403)
    role = user["role"]
    fecha_desde, fecha_hasta, grupo, alumno, gravedad, profesor_id = _base_filters(request)

    # --------------------------------------------------
    # Decisión por rol + carga de incidencias
    # --------------------------------------------------
    if role in ROLES_VEN_TODAS:
        incidents = get_incidents(
            mode="all",
            profesor_id=profesor_id,
            grupo=grupo,
            alumno=alumno,
            gravedad=gravedad,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
        show_profesor_filter = True

    elif role in ROLES_VEN_PROPIAS:
        incidents = get_incidents(
            mode="own",
            user_id=user["id"],
            grupo=grupo,
            alumno=alumno,
            gravedad=gravedad,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
        show_profesor_filter = False

    else:
        raise HTTPException(status_code=403)

    # --------------------------------------------------
    # Datos para desplegables de filtros
    # --------------------------------------------------
    grupos = get_all_groups()

    alumnos = get_students_by_group(grupo) if grupo else []

    profesores = get_all_teachers() if show_profesor_filter else []

    # --------------------------------------------------
    # Render
    # --------------------------------------------------
    return request.app.state.templates.TemplateResponse(
        "incidents/list.html",
        ctx(
            request,
            user=user,
            title="Listado de incidencias",
            incidents=incidents,
            PERM_EDITAR_INCIDENCIA=PERM_EDITAR_INCIDENCIA,
            filters={
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
                "grupo": grupo,
                "alumno": alumno,
                "gravedad": gravedad,
                "profesor_id": profesor_id if show_profesor_filter else None,
            },
            show_profesor_filter=show_profesor_filter,
            show_group_filter=True,
            list_title="Listado de incidencias" if role in ROLES_VEN_TODAS else "Mis incidencias",
            grupos=grupos,
            alumnos=alumnos,
            profesores=profesores,
        ),
    )


@router.get("/incidents/tutoria", response_class=HTMLResponse)
def incidents_tutoria(request: Request, user: dict = Depends(load_user_dep)):
    if not has_permission(user, PERM_LISTAR_INCIDENCIAS):
        raise HTTPException(status_code=403)
    if user["role"] not in ROLES_VEN_PROPIAS:
        raise HTTPException(status_code=403)

    tutor_group = (user.get("tutor") or "").strip()
    if not tutor_group:
        raise HTTPException(status_code=403)

    fecha_desde, fecha_hasta, _grupo, alumno, gravedad, _profesor_id = _base_filters(request)

    incidents = get_incidents(
        mode="all",
        grupo=tutor_group,
        alumno=alumno,
        gravedad=gravedad,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
    alumnos = get_students_by_group(tutor_group)

    return request.app.state.templates.TemplateResponse(
        "incidents/list.html",
        ctx(
            request,
            user=user,
            title="Mi tutoría",
            incidents=incidents,
            PERM_EDITAR_INCIDENCIA=PERM_EDITAR_INCIDENCIA,
            filters={
                "fecha_desde": fecha_desde,
                "fecha_hasta": fecha_hasta,
                "grupo": tutor_group,
                "alumno": alumno,
                "gravedad": gravedad,
                "profesor_id": None,
            },
            show_profesor_filter=False,
            show_group_filter=False,
            list_title=f"Incidencias de mi tutoría ({tutor_group})",
            grupos=[],
            alumnos=alumnos,
            profesores=[],
        ),
    )
