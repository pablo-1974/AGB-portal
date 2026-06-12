# routers/analysis_student.py

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from datetime import date

from auth import load_user_dep
from context import ctx

from db.incidents import get_incidents
from db.school_calendar import get_course_start_iso
from db.students import get_all_groups, get_students_by_group
from utils.enums import GRAVEDAD_MUY_GRAVE

from utils.permissions import has_permission
from utils.enums import PERM_HISTORIAL_ALUMNO

router = APIRouter()


@router.get("/analysis/student", response_class=HTMLResponse)
def analysis_student(
    request: Request,
    grupo: str | None = None,
    alumno: str | None = None,
    from_: str | None = None,
    to: str | None = None,
    user=Depends(load_user_dep),
):
    
    # ✅ CONTROL DE PERMISOS (PASO 5)
    if not has_permission(user, PERM_HISTORIAL_ALUMNO):
        raise HTTPException(status_code=403)

    """
    Historial de incidencias por alumno / grupo / global.
    """

    # --------------------------------------------------
    # 1. Fechas por defecto
    # --------------------------------------------------
    fecha_desde = from_ or get_course_start_iso()
    fecha_hasta = to or date.today().isoformat()

    # --------------------------------------------------
    # 2. Filtros disponibles
    # --------------------------------------------------
    grupos = get_all_groups()
    alumnos = get_students_by_group(grupo) if grupo else []

    # --------------------------------------------------
    # 3. Incidencias filtradas
    # --------------------------------------------------
    rows_raw = get_incidents(
        mode="all",
        grupo=grupo,
        alumno=alumno,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )

    # --------------------------------------------------
    # 4. Incidencias totales del sistema (mismo periodo)
    # --------------------------------------------------
    total_rows_raw = get_incidents(
        mode="all",
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )

    total_sistema = len(total_rows_raw)
    total_filtrado = len(rows_raw)

    if alumno:
        kpi_filtrado_label = f"Incidencias del alumno {alumno}"
    elif grupo:
        kpi_filtrado_label = f"Incidencias del grupo {grupo}"
    else:
        kpi_filtrado_label = "Incidencias filtradas"

    # --------------------------------------------------
    # 5. Preparar filas y KPIs de detalle
    # --------------------------------------------------
    rows = []
    abiertas = 0
    muy_graves = 0

    for r in rows_raw:
        gravedad_ini = r["gravedad_inicial"]
        gravedad_fin = r["gravedad_final"]
        estado = r["estado"]

        if estado != "cerrado":
            abiertas += 1

        if gravedad_ini == GRAVEDAD_MUY_GRAVE:
            muy_graves += 1

        rows.append({
            "fecha": r["fecha"],
            "hora": r["franja"],
            "grupo": r["grupo"],
            "alumno": r["alumno"],
            "profesor": r["teacher_name"],
            "descripcion": r["descripcion"],
            "grav_ini": gravedad_ini,
            "grav_fin": gravedad_fin,
            "estado": estado,
        })

    kpis_detalle = {
        "total": len(rows),
        "abiertas": abiertas,
        "muy_graves": muy_graves,
    }

    # --------------------------------------------------
    # 6. Render
    # --------------------------------------------------
    return request.app.state.templates.TemplateResponse(
        "student_analysis.html",
        ctx(
            request,
            user,
            title="Historial por alumno",
            grupos=grupos,
            alumnos=alumnos,
            grupo_sel=grupo,
            alumno_sel=alumno,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            rows=rows,
            kpis=kpis_detalle,
            kpi_total_sistema=total_sistema,
            kpi_filtrado=total_filtrado,
            kpi_filtrado_label=kpi_filtrado_label,
        ),
    )
