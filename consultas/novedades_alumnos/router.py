"""Rutas HTTP bajo ``/novedades-alumnos``."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from auth import load_user_dep
from context import ctx
from db.expedientes_disciplinarios import (
    list_expedientes_abiertos,
    list_expedientes_cerrados,
)
from db.paa_procedimientos import list_paa_procedimientos
from db.portal_published_notices import (
    list_baja_alumno_notices,
    list_nuevo_alumno_notices,
)

router = APIRouter(prefix="/novedades-alumnos", tags=["novedades-alumnos"])

_VISTAS = frozenset({"altas", "bajas", "sanciones"})


def _vista(raw: str | None) -> str | None:
    v = (raw or "").strip().lower()
    return v if v in _VISTAS else None


def _format_date_display(d: date | None) -> str:
    if d is None:
        return "—"
    return d.strftime("%d/%m/%Y")


def _format_range_display(inicio: date | None, final: date | None) -> str:
    if inicio is None or final is None:
        return "—"
    return f"de {_format_date_display(inicio)} a {_format_date_display(final)}"


def _paa_rows_for_display() -> list[dict]:
    out: list[dict] = []
    for r in list_paa_procedimientos():
        fi = r.get("fecha_inicio")
        ff = r.get("fecha_final")
        out.append(
            {
                **r,
                "fecha_inicio_display": _format_date_display(
                    fi if isinstance(fi, date) else None
                ),
                "fecha_final_display": _format_date_display(
                    ff if isinstance(ff, date) else None
                ),
            }
        )
    return out


def _expedientes_rows_for_display(raw_rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for r in raw_rows:
        fi = r.get("fecha_inicio_expediente")
        ff = r.get("fecha_final_expediente")
        ci = r.get("cautelar_inicio")
        cf = r.get("cautelar_final")
        si = r.get("sancion_inicio")
        sf = r.get("sancion_final")
        out.append(
            {
                **r,
                "inicio_expediente_display": _format_date_display(
                    fi if isinstance(fi, date) else None
                ),
                "final_expediente_display": _format_date_display(
                    ff if isinstance(ff, date) else None
                ),
                "cautelar_display": _format_range_display(
                    ci if isinstance(ci, date) else None,
                    cf if isinstance(cf, date) else None,
                ),
                "sancion_display": _format_range_display(
                    si if isinstance(si, date) else None,
                    sf if isinstance(sf, date) else None,
                ),
            }
        )
    return out


@router.get("/", response_class=HTMLResponse)
def novedades_alumnos_home(
    request: Request,
    user: dict = Depends(load_user_dep),
    vista: str | None = Query(default=None),
):
    active = _vista(vista)
    alumnos_nuevos: list = []
    alumnos_baja: list = []
    procedimientos_paa: list = []
    expedientes_abiertos: list = []
    expedientes_cerrados: list = []
    if active == "altas":
        alumnos_nuevos = list_nuevo_alumno_notices()
    elif active == "bajas":
        alumnos_baja = list_baja_alumno_notices()
    elif active == "sanciones":
        procedimientos_paa = _paa_rows_for_display()
        expedientes_abiertos = _expedientes_rows_for_display(list_expedientes_abiertos())
        expedientes_cerrados = _expedientes_rows_for_display(list_expedientes_cerrados())

    return request.app.state.templates.TemplateResponse(
        "novedades_alumnos/index.html",
        ctx(
            request,
            user=user,
            title="Novedades alumnos",
            portal_shell_title="Novedades alumnos",
            vista=active,
            alumnos_nuevos=alumnos_nuevos,
            alumnos_baja=alumnos_baja,
            procedimientos_paa=procedimientos_paa,
            expedientes_abiertos=expedientes_abiertos,
            expedientes_cerrados=expedientes_cerrados,
        ),
    )
