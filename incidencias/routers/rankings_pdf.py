# routers/rankings_pdf.py

from collections import Counter
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from auth import load_user_dep
from db.incidents import get_incidents
from db.sanciones_ranking import ranking_dias_sancion
from db.school_calendar import get_course_start_iso
from utils.enums import (
    PERM_RANKING_ALUMNOS,
    PERM_RANKING_GRUPOS,
    PERM_RANKING_PROFESORES,
)
from utils.pdf_rankings import pdf_rankings
from utils.permissions import has_permission

router = APIRouter()

_METRICS = frozenset({"incidencias", "sanciones"})


def _normalize_metric(raw: str | None, *, mode: str) -> str:
    m = (raw or "incidencias").strip().lower()
    if mode == "profesores":
        return "incidencias"
    return m if m in _METRICS else "incidencias"


@router.get("/rankings/pdf")
def rankings_pdf(
    request: Request,
    mode: str = "alumnos",
    metric: str | None = None,
    gravedad: str | None = None,
    grupo: str | None = None,
    from_: str | None = None,
    to: str | None = None,
    user=Depends(load_user_dep),
):
    if mode == "alumnos":
        if not has_permission(user, PERM_RANKING_ALUMNOS):
            raise HTTPException(status_code=403)
    elif mode == "grupos":
        if not has_permission(user, PERM_RANKING_GRUPOS):
            raise HTTPException(status_code=403)
    else:
        mode = "profesores"
        if not has_permission(user, PERM_RANKING_PROFESORES):
            raise HTTPException(status_code=403)

    metric_n = _normalize_metric(metric, mode=mode)
    fecha_desde = from_ or get_course_start_iso()
    fecha_hasta = to or date.today().isoformat()

    if mode == "alumnos":
        columna = "Alumno"
        if metric_n == "sanciones":
            titulo = (
                f"Ranking de alumnos de {grupo} · Días de sanción"
                if grupo
                else "Ranking de alumnos · Días de sanción"
            )
        elif grupo:
            titulo = f"Ranking de alumnos de {grupo}"
        else:
            titulo = "Ranking de alumnos · Partes de incidencias"
    elif mode == "grupos":
        columna = "Grupo"
        titulo = (
            "Ranking de grupos · Días de sanción"
            if metric_n == "sanciones"
            else "Ranking de grupos · Partes de incidencias"
        )
    else:
        columna = "Profesor"
        titulo = "Ranking de profesores"

    if metric_n == "sanciones":
        rows = ranking_dias_sancion(mode=mode, grupo=grupo)
        col_total = "Días de sanción"
        show_periodo = False
        filename = "ranking_dias_sancion.pdf"
    else:
        rows_raw = get_incidents(
            mode="all",
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
        )
        counter = Counter()
        alumno_grupo = {}
        for r in rows_raw:
            grav_real = r["gravedad_final"] or r["gravedad_inicial"]
            if gravedad and grav_real != gravedad:
                continue
            if mode == "alumnos":
                if grupo and r["grupo"] != grupo:
                    continue
                key = r["alumno"]
                alumno_grupo[key] = r["grupo"]
            elif mode == "grupos":
                key = r["grupo"]
            else:
                key = r["teacher_name"]
            if key:
                counter[key] += 1
        if mode == "alumnos":
            rows = [
                {
                    "nombre": alumno,
                    "grupo": alumno_grupo.get(alumno),
                    "total": total,
                }
                for alumno, total in counter.most_common()
            ]
        else:
            rows = [{"nombre": k, "total": v} for k, v in counter.most_common()]
        col_total = "Incidencias"
        show_periodo = True
        filename = "ranking_incidencias.pdf"

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No hay datos para generar el ranking",
        )

    pdf_bytes = pdf_rankings(
        rows=rows,
        titulo=titulo,
        columna=columna,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        logo_path=Path("static/logo.png"),
        col_total=col_total,
        show_periodo=show_periodo,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        },
    )
