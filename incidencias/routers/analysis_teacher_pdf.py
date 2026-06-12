# routers/analysis_teacher_pdf.py

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import Response
from datetime import date
from pathlib import Path

from auth import load_user_dep
from db.incidents import get_incidents
from db.school_calendar import get_course_start_iso
from utils.pdf_teacher_history import pdf_teacher_history

from utils.permissions import has_permission
from utils.enums import PERM_HISTORIAL_PROFESOR

router = APIRouter()


@router.get("/analysis/teacher/pdf")
def analysis_teacher_pdf(
    request: Request,
    profesor: str | None = None,
    grupo: str | None = None,
    alumno: str | None = None,
    from_: str | None = None,
    to: str | None = None,
    user=Depends(load_user_dep),
):
    """
    PDF de historial de incidencias por profesor.
    
    - Requiere profesor seleccionado
    """
    
    # ✅ CONTROL DE PERMISOS (PASO 5)
    if not has_permission(user, PERM_HISTORIAL_PROFESOR):
        raise HTTPException(status_code=403)

    # --------------------------------------------------
    # 1. Fechas por defecto
    # --------------------------------------------------
    fecha_desde = from_ or get_course_start_iso()
    fecha_hasta = to or date.today().isoformat()

    # --------------------------------------------------
    # 2. Cargar incidencias
    # --------------------------------------------------
    rows_raw = get_incidents(
        mode="all",
        grupo=grupo,
        alumno=alumno,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )

    # --------------------------------------------------
    # 3. Preparar filas
    # --------------------------------------------------
    if profesor:
        rows_raw = [
            r for r in rows_raw
            if r["teacher_name"] == profesor
        ]
    else:
        rows_raw = []
    
    if not rows_raw:
        raise HTTPException(
            status_code=404,
            detail="No hay incidencias para los filtros seleccionados",
        )
    
    rows = []
    
    for r in rows_raw:
        rows.append({
            "fecha": r["fecha"],
            "hora": r["franja"] or "",
            "grupo": r["grupo"],
            "alumno": r["alumno"],
            "gravedad": r["gravedad_final"] or r["gravedad_inicial"],
            "descripcion": r["descripcion"],
        })

    # --------------------------------------------------
    # 4. Título del PDF
    # --------------------------------------------------
    if profesor:
        titulo = f"Historial de incidencias del profesor {profesor}"
    else:
        titulo = "Historial de incidencias por profesor"

    # --------------------------------------------------
    # 5. Generar PDF (devuelve BYTES)
    # --------------------------------------------------
    pdf_bytes = pdf_teacher_history(
        rows=rows,
        titulo=titulo,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        logo_path=Path("static/logo.png"),
    )

    # --------------------------------------------------
    # 6. Respuesta correcta
    # --------------------------------------------------
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=historial_profesor.pdf"
        },
    )
