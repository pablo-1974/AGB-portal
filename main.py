"""
Portal único del campus + apps integradas (monolito FastAPI).
Sesión en cookie compartida.
"""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from auth import redirect_portal_or_login
from config import settings
from context import ctx
from db.users import get_user_by_id, has_any_user
from db.groups import ensure_groups_schema
from db.students import ensure_students_schema
from db.enrolled_subjects import ensure_enrolled_subjects_schema
from db.enrolled_subject_catalog import ensure_subject_catalog_schema
from db.moscosos_calendar import ensure_moscosos_calendar_schema
from db.school_calendar import ensure_school_calendar_schema
from db.moscosos_reservations import ensure_moscosos_reservations_schema
from db.funcionamiento_portal_feedback import ensure_funcionamiento_portal_feedback_schema
from db.mantenimiento_feedback import ensure_mantenimiento_feedback_schema
from db.listados_feedback import ensure_listados_feedback_schema
from db.extraescolares_schema import ensure_extraescolares_schema
from reservas.db import ensure_reservas_schema
from ausencias.db import ensure_ausencias_schema
from db.action_logs import ensure_action_logs_schema
from db.reservas_access import ensure_reservas_normas_schema, has_accepted_reservas_normas

from routers.change_password import router as change_password_router
from routers.first_login import router as first_login_router
from routers.login import router as login_router
from routers.portal import router as portal_router
from routers.register_first import router as register_first_router

from ausencias.router import router as ausencias_router
from buzones.router import router as buzones_router
from consultas.cuaderno.router import router as cuaderno_router
from consultas.documentos.router import router as documentos_router
from consultas.listados.router import router as listados_router
from moscosos.router import router as moscosos_router
from extraescolares.router import router as extraescolares_router
from reservas.router import router as reservas_router

from administrador.bootstrap import ADMIN_ROUTERS, load_router as load_admin_router
from administrador.routers.admin_school_calendar import router as admin_school_calendar_router
from incidencias.bootstrap import load_router as load_incidencias_router
from db.enrolled_subject_catalog import build_bach_pendientes_resumen
import consultas.listados.asignaturas_queries as _asignaturas_queries


def _build_bach_pendientes_resumen_patched(*, pendientes, catalog_rows):
    _ = catalog_rows
    return build_bach_pendientes_resumen(pendientes)


_asignaturas_queries._build_bach_pendientes_resumen = _build_bach_pendientes_resumen_patched


INCIDENCIAS_ROUTERS = (
    "dashboard",
    "analysis_student",
    "analysis_teacher",
    "analysis_student_pdf",
    "analysis_teacher_pdf",
    "analysis_excursion",
    "analysis_excursion_pdf",
    "rankings",
    "rankings_pdf",
    "counters",
    "convivencia_dashboard",
    "profesor_dashboard",
    "incidents_create",
    "incidents_list",
    "incidents_close",
    "incidents_edit",
    "incidents_print",
)

app = FastAPI(title=settings.PORTAL_APP_NAME)
ensure_reservas_schema()
ensure_groups_schema()
ensure_students_schema()
ensure_enrolled_subjects_schema()
ensure_subject_catalog_schema()
ensure_moscosos_calendar_schema()
ensure_school_calendar_schema()
ensure_moscosos_reservations_schema()
ensure_funcionamiento_portal_feedback_schema()
ensure_mantenimiento_feedback_schema()
ensure_listados_feedback_schema()
ensure_extraescolares_schema()
ensure_ausencias_schema()
ensure_action_logs_schema()
ensure_reservas_normas_schema()


class ReservasNormasMiddleware(BaseHTTPMiddleware):
    """Redirige a normas de uso en la primera visita a /reservas (tras cargar sesión)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/reservas") and not path.startswith(
            ("/reservas/normas-uso", "/reservas/reservar")
        ):
            user_id = request.session.get("user_id")
            if user_id is not None and not has_accepted_reservas_normas(
                user_id=int(user_id)
            ):
                return RedirectResponse("/reservas/normas-uso", status_code=303)
        return await call_next(request)


app.add_middleware(ReservasNormasMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="campus_portal_session",
    max_age=60 * 60 * 8,
    same_site="lax",
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

_template_dirs = [
    str(BASE_DIR / "templates"),
    str(BASE_DIR / "administrador" / "templates"),
    str(BASE_DIR / "incidencias" / "templates"),
    str(BASE_DIR / "reservas" / "templates"),
    str(BASE_DIR / "ausencias" / "templates"),
    str(BASE_DIR / "consultas" / "listados" / "templates"),
    str(BASE_DIR / "consultas" / "cuaderno" / "templates"),
    str(BASE_DIR / "consultas" / "documentos" / "templates"),
    str(BASE_DIR / "moscosos" / "templates"),
    str(BASE_DIR / "extraescolares" / "templates"),
    str(BASE_DIR / "buzones" / "funcionamiento_portal" / "templates"),
    str(BASE_DIR / "buzones" / "mantenimiento" / "templates"),
    str(BASE_DIR / "buzones" / "listados" / "templates"),
]
templates = Jinja2Templates(directory=_template_dirs, auto_reload=True)


def _jinja_reservar_url(reservation_date: str, room: str, slot: str) -> str:
    from urllib.parse import quote

    return (
        f"/reservas/reservar?reservation_date={quote(str(reservation_date), safe='')}"
        f"&room={quote(str(room), safe='')}"
        f"&slot={quote(str(slot), safe='')}"
    )


def _jinja_cuadrantes_week_nav(week_start: str) -> dict[str, str | None]:
    from datetime import date

    from reservas.db import build_week_nav, course_bounds_for_week, get_week_bounds

    try:
        day = date.fromisoformat(str(week_start).strip()[:10])
    except ValueError:
        day = date.today()
    monday, _ = get_week_bounds(day)
    first, last = course_bounds_for_week(monday)
    return build_week_nav(monday, school_first=first, school_last=last)


templates.env.filters["reservar_url"] = _jinja_reservar_url
templates.env.globals["reservar_url"] = _jinja_reservar_url
templates.env.globals["cuadrantes_week_nav"] = _jinja_cuadrantes_week_nav
app.state.templates = templates


@app.exception_handler(HTTPException)
async def _http_exception_handler(request: Request, exc: HTTPException):
    accept = (request.headers.get("accept") or "").lower()
    if "text/html" in accept:
        if exc.status_code == 401:
            return RedirectResponse("/login", status_code=303)
        if exc.status_code == 403:
            path = request.url.path or ""
            if path.startswith("/listados"):
                user_id = request.session.get("user_id")
                user = get_user_by_id(int(user_id)) if user_id else None
                return request.app.state.templates.TemplateResponse(
                    "listados/forbidden.html",
                    ctx(
                        request,
                        user=user,
                        title="Listados · Sin permiso",
                        detail=exc.detail or "No tienes permiso para esta consulta.",
                    ),
                    status_code=403,
                )
            return redirect_portal_or_login(request)
        headers = getattr(exc, "headers", None)
   
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)


app.include_router(login_router)
app.include_router(register_first_router)
app.include_router(first_login_router)
app.include_router(portal_router)
app.include_router(listados_router)
app.include_router(cuaderno_router)
app.include_router(documentos_router)
app.include_router(change_password_router)
app.include_router(ausencias_router)
app.include_router(reservas_router)
app.include_router(moscosos_router)
app.include_router(extraescolares_router)
app.include_router(buzones_router)

app.include_router(admin_school_calendar_router)

for _stem in ADMIN_ROUTERS:
    app.include_router(load_admin_router(_stem))

for _stem in INCIDENCIAS_ROUTERS:
    app.include_router(load_incidencias_router(_stem))


@app.api_route("/consultas", methods=["GET", "HEAD"])
@app.api_route("/consultas/", methods=["GET", "HEAD"])
def _legacy_consultas_hub_redirect():
    """Ruta antigua renombrada a ``/listados``."""
    return RedirectResponse("/listados/", status_code=307)


@app.api_route("/consultas/{subpath:path}", methods=["GET", "HEAD"])
def _legacy_consultas_subpath_redirect(subpath: str):
    subpath = (subpath or "").lstrip("/")
    dest = f"/listados/{subpath}" if subpath else "/listados/"
    return RedirectResponse(dest, status_code=307)


@app.api_route("/", methods=["GET", "HEAD"])
def root(request: Request):
    if request.method == "HEAD":
        return JSONResponse({"ok": True})

    if not has_any_user():
        return RedirectResponse("/register-first", status_code=303)

    if not request.session.get("user_id"):
        return RedirectResponse("/login", status_code=303)

    return RedirectResponse("/portal", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}
