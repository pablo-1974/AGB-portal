# routers/analysis_excursion_pdf.py

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import Response
from datetime import date
from pathlib import Path
from dateutil.relativedelta import relativedelta

from auth import load_user_dep
from db.incidents import get_excursion_eligibility
from utils.pdf_excursion import pdf_no_aptos_excursion

from utils.permissions import has_permission
from utils.enums import PERM_EXCURSION

router = APIRouter()


@router.get("/analysis/excursion/pdf")
def analysis_excursion_pdf(
    request: Request,
    actividad: str | None = None,
    fecha_excursion: str | None = None,
    grupos: list[str] | None = Query(None),
    user=Depends(load_user_dep),
):
    """
    PDF de alumnos no aptos para una excursión.

    - Requiere actividad, fecha_excursion y al menos un grupo
    - Solo genera PDF si hay sancionados
    """

    # ✅ CONTROL DE PERMISOS (PASO 5)
    if not has_permission(user, PERM_EXCURSION):
        raise HTTPException(status_code=403)

    # --------------------------------------------------
    # 1. Validación básica
    # --------------------------------------------------
    if not actividad or not actividad.strip():
        raise HTTPException(400, detail="Falta el nombre de la actividad")

    if not fecha_excursion:
        raise HTTPException(400, detail="Falta la fecha de la excursión")

    if not grupos:
        raise HTTPException(400, detail="Debes indicar al menos un grupo")

    # --------------------------------------------------
    # 2. Cálculo de fechas
    # --------------------------------------------------
    fecha_exc = date.fromisoformat(fecha_excursion)
    fecha_desde = fecha_exc - relativedelta(months=1)
    fecha_hasta = fecha_exc - relativedelta(days=1)

    # --------------------------------------------------
    # 3. Cálculo de elegibilidad
    # --------------------------------------------------
    sancionados, _amnistiables = get_excursion_eligibility(
        fecha_excursion=fecha_excursion,
        grupos=grupos,
    )

    if not sancionados:
        raise HTTPException(
            status_code=404,
            detail="No hay alumnos no aptos para la excursión",
        )

    # --------------------------------------------------
    # 4. Generar PDF
    # --------------------------------------------------
    pdf_bytes = pdf_no_aptos_excursion(
        rows=sancionados,
        actividad=actividad,
        fecha_excursion=fecha_exc,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        logo_path=Path("static/logo.png"),
    )

    fname = f"no_aptos_{actividad.replace(' ', '_')}_{fecha_excursion}.pdf"

    # --------------------------------------------------
    # 5. Respuesta
    # --------------------------------------------------
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"'
        },
    )
