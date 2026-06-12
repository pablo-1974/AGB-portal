# routers/analysis_excursion.py

from fastapi import APIRouter, Request, Depends, Query, HTTPException
from fastapi.responses import HTMLResponse
from datetime import date
from dateutil.relativedelta import relativedelta

from auth import load_user_dep
from context import ctx
from db.students import get_all_groups
from db.incidents import get_excursion_eligibility

from utils.permissions import has_permission
from utils.enums import PERM_EXCURSION

router = APIRouter()


@router.get("/analysis/excursion", response_class=HTMLResponse)
def analysis_excursion(
    request: Request,
    actividad: str | None = None,
    fecha_excursion: str | None = None,
    grupos: list[str] | None = Query(None),
    user=Depends(load_user_dep),
):
    if not has_permission(user, PERM_EXCURSION):
        raise HTTPException(status_code=403)
        
    grupos_all = get_all_groups()

    sancionados = []
    amnistiables = []
    fecha_desde = None
    fecha_hasta = None
    error = None

    if actividad or fecha_excursion or grupos:
        if not actividad or not fecha_excursion or not grupos:
            error = "Debes indicar actividad, fecha y al menos un grupo."
        else:
            fecha_exc = date.fromisoformat(fecha_excursion)
            sancionados, amnistiables = get_excursion_eligibility(
                fecha_excursion=fecha_excursion,
                grupos=grupos,
            )

            fecha_desde = fecha_exc - relativedelta(months=1)
            fecha_hasta = fecha_exc - relativedelta(days=1)

    return request.app.state.templates.TemplateResponse(
        "analysis_excursion.html",
        ctx(
            request,
            user,
            title="Filtrar excursión",
            actividad=actividad,
            fecha_excursion=fecha_excursion,
            grupos_all=grupos_all,
            grupos_sel=grupos or [],
            sancionados=sancionados,
            amnistiables=amnistiables,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            error=error,
        ),
    )
