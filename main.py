"""
Portal único del campus + apps integradas (monolito FastAPI).
Sesión en cookie compartida.
"""

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Paquetes locales (pydeps); regrabado 2026-08-22 12:26 Comodo off
_local_deps = BASE_DIR / "pydeps"
if _local_deps.is_dir():
    sys.path.insert(0, str(_local_deps))

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env", override=True)
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from auth import redirect_portal_or_login
from config import settings
from context import ctx
from db.users import get_user_by_id, has_any_user
from utils.permissions import is_invitado
from db.groups import ensure_groups_schema
from db.departamentos import ensure_departamentos_schema
from db.students import ensure_students_schema
from db.enrolled_subjects import ensure_enrolled_subjects_schema
from db.enrolled_subject_catalog import (
    build_bach_pendientes_resumen,
    ensure_subject_catalog_schema,
)
from db.moscosos_calendar import ensure_moscosos_calendar_schema
from db.school_calendar import ensure_school_calendar_schema
from db.moscosos_reservations import ensure_moscosos_reservations_schema
from db.funcionamiento_portal_feedback import ensure_funcionamiento_portal_feedback_schema
from db.mantenimiento_feedback import ensure_mantenimiento_feedback_schema
from db.listados_feedback import ensure_listados_feedback_schema
from db.extraescolares_schema import ensure_extraescolares_schema
from db.portal_published_notices import ensure_portal_published_notices_schema
from db.portal_espacios import (
    ensure_portal_espacios_schema,
    espacio_access_for_user,
    resolve_espacio_id_for_path,
)
from db.competencias_clave import ensure_competencias_clave_schema
from db.competencias_materia_criterios import ensure_competencias_materia_criterios_schema
from db.competencias_materia_variables import ensure_competencias_materia_variables_schema
from db.competencias_evaluacion import ensure_competencias_evaluacion_schema
from db.competencias_pd_porcentajes import ensure_competencias_pd_porcentajes_schema
from db.competencias_fechas_sesion import ensure_competencias_fechas_sesion_schema
from db.competencias_calculo_config import ensure_competencias_calculo_config_schema
from db.competencias_alumno_descriptor import ensure_competencias_alumno_descriptor_schema
from db.competencias_alumno_competencia import ensure_competencias_alumno_competencia_schema
from db.competencias_recalc import ensure_competencias_recalc_schema
from db.competencias_bach_ordinaria import ensure_competencias_bach_ordinaria_schema
from db.competencias_sesion_notas import ensure_competencias_sesion_notas_schema
from db.paa_procedimientos import ensure_paa_procedimientos_schema
from db.expedientes_disciplinarios import ensure_expedientes_disciplinarios_schema
from db.portal_welcome import (
    ensure_portal_welcome_schema,
    has_accepted_portal_welcome,
)
from reservas.db import ensure_reservas_schema
from ausencias.db import ensure_ausencias_schema
from db.action_logs import ensure_action_logs_schema
from db.moscosos_access import (
    ensure_moscosos_normas_schema,
    has_accepted_moscosos_normas,
)
from db.extraescolares_access import (
    ensure_extraescolares_normas_schema,
    has_accepted_extraescolares_normas,
)
from db.incidencias_access import (
    ensure_incidencias_normas_schema,
    has_accepted_incidencias_normas,
)
from db.competencias_access import (
    ensure_competencias_normas_schema,
    has_accepted_competencias_normas,
)
from db.reservas_access import ensure_reservas_normas_schema, has_accepted_reservas_normas

from routers.change_password import router as change_password_router
from routers.first_login import router as first_login_router
from routers.login import router as login_router
from routers.portal import router as portal_router
from routers.portal_welcome import router as portal_welcome_router
from routers.register_first import router as register_first_router
from routers.espacios_obras import router as espacios_obras_router
from routers.admin_espacios_visibles import router as admin_espacios_visibles_router
from routers.admin_sanciones import router as admin_sanciones_router
from routers.moscosos_reservar import router as moscosos_reservar_router
from routers.moscosos_staff import router as moscosos_staff_router

from ausencias.router import router as ausencias_router
from buzones.router import router as buzones_router
from consultas.cuaderno.router import router as cuaderno_router
from consultas.documentos.router import router as documentos_router
from consultas.jefatura.router import router as documentos_jefatura_router
from consultas.listados.router import router as listados_router
from consultas.novedades_alumnos.router import router as novedades_alumnos_router
from moscosos.router import router as moscosos_router
from extraescolares.router import router as extraescolares_router
from publicar_avisos.router import router as publicar_avisos_router
from competencias.router import router as competencias_router
from reservas.router import router as reservas_router

from administrador.bootstrap import ADMIN_ROUTERS, load_router as load_admin_router
from administrador.routers.admin_school_calendar import router as admin_school_calendar_router
from incidencias.bootstrap import load_router as load_incidencias_router
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
    "incidents_normas",
    "incidents_create",
    "incidents_list",
    "incidents_close",
    "incidents_edit",
    "incidents_print",
)

app = FastAPI(
    title=settings.PORTAL_APP_NAME,
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
)
ensure_reservas_schema()
ensure_groups_schema()
ensure_departamentos_schema()
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
ensure_portal_published_notices_schema()
ensure_paa_procedimientos_schema()
ensure_expedientes_disciplinarios_schema()
ensure_portal_welcome_schema()
ensure_portal_espacios_schema()
ensure_competencias_clave_schema()
ensure_competencias_materia_criterios_schema()
ensure_competencias_pd_porcentajes_schema()
ensure_competencias_materia_variables_schema()
ensure_competencias_evaluacion_schema()
ensure_competencias_fechas_sesion_schema()
ensure_competencias_calculo_config_schema()
ensure_competencias_alumno_descriptor_schema()
ensure_competencias_alumno_competencia_schema()
ensure_competencias_recalc_schema()
ensure_competencias_sesion_notas_schema()
ensure_competencias_bach_ordinaria_schema()
ensure_ausencias_schema()
ensure_action_logs_schema()
ensure_reservas_normas_schema()
ensure_moscosos_normas_schema()
ensure_extraescolares_normas_schema()
ensure_incidencias_normas_schema()
ensure_competencias_normas_schema()


def _path_matches_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?")


def _is_incidencias_app_path(path: str) -> bool:
    """Rutas de la app Incidencias (no hay prefijo /incidencias)."""
    if path.startswith("/incidents/normas"):
        return False
    exact = {"/dashboard", "/counters", "/rankings", "/admin/dashboard"}
    if path in exact:
        return True
    for prefix in (
        "/profesor",
        "/convivencia",
        "/incidents",
        "/analysis",
        "/rankings",
        "/counters",
        "/admin/sanciones",
    ):
        if _path_matches_prefix(path, prefix):
            return True
    if _path_matches_prefix(path, "/admin/dashboard"):
        return True
    if _path_matches_prefix(path, "/dashboard"):
        return True
    return False


def _session_user_is_invitado(request: Request) -> bool:
    uid = request.session.get("user_id")
    if uid is None:
        uid = request.session.get("first_login_user_id")
    if uid is None:
        return False
    return is_invitado(get_user_by_id(int(uid)))


class ReservasNormasMiddleware(BaseHTTPMiddleware):
    """Redirige a normas de uso en la primera visita a /reservas (tras cargar sesión)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/reservas") and not path.startswith(
            ("/reservas/normas-uso", "/reservas/reservar")
        ):
            user_id = request.session.get("user_id")
            if user_id is not None and not _session_user_is_invitado(request) and not has_accepted_reservas_normas(
                user_id=int(user_id)
            ):
                return RedirectResponse("/reservas/normas-uso", status_code=303)
        return await call_next(request)


class MoscososNormasMiddleware(BaseHTTPMiddleware):
    """Redirige a normas de reserva en la primera visita a /moscosos."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/moscosos") and not path.startswith(
            "/moscosos/normas-reserva"
        ):
            user_id = request.session.get("user_id")
            if user_id is not None and not _session_user_is_invitado(request) and not has_accepted_moscosos_normas(
                user_id=int(user_id)
            ):
                return RedirectResponse("/moscosos/normas-reserva", status_code=303)
        return await call_next(request)


class ExtraescolaresNormasMiddleware(BaseHTTPMiddleware):
    """Redirige a normas en la primera visita a /extraescolares."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/extraescolares") and not path.startswith(
            "/extraescolares/normas"
        ):
            user_id = request.session.get("user_id")
            if user_id is not None and not _session_user_is_invitado(request) and not has_accepted_extraescolares_normas(
                user_id=int(user_id)
            ):
                return RedirectResponse("/extraescolares/normas", status_code=303)
        return await call_next(request)


class IncidenciasNormasMiddleware(BaseHTTPMiddleware):
    """Redirige a normas en la primera visita a la app de incidencias."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if _is_incidencias_app_path(path):
            user_id = request.session.get("user_id")
            if user_id is not None and not _session_user_is_invitado(request) and not has_accepted_incidencias_normas(
                user_id=int(user_id)
            ):
                return RedirectResponse("/incidents/normas", status_code=303)
        return await call_next(request)


class CompetenciasNormasMiddleware(BaseHTTPMiddleware):
    """Redirige a normas en la primera visita a Evaluación de competencias."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/competencias") and not path.startswith(
            "/competencias/normas"
        ):
            user_id = request.session.get("user_id")
            if (
                user_id is not None
                and not _session_user_is_invitado(request)
                and not has_accepted_competencias_normas(user_id=int(user_id))
            ):
                return RedirectResponse("/competencias/normas", status_code=303)
        return await call_next(request)


app.add_middleware(ReservasNormasMiddleware)
app.add_middleware(MoscososNormasMiddleware)
app.add_middleware(ExtraescolaresNormasMiddleware)
app.add_middleware(IncidenciasNormasMiddleware)
app.add_middleware(CompetenciasNormasMiddleware)


_ESPACIOS_VISIBILITY_EXEMPT_PREFIXES = (
    "/login",
    "/logout",
    "/first-login",
    "/register-first",
    "/portal",
    "/espacios/en-obras",
    "/admin/espacios-visibles",
    "/static",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/change-password",
)


class EspaciosVisibilityMiddleware(BaseHTTPMiddleware):
    """Aplica visible / en obras / no visible a las rutas de cada espacio."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        for prefix in _ESPACIOS_VISIBILITY_EXEMPT_PREFIXES:
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                return await call_next(request)
            if path.rstrip("/") == prefix.rstrip("/"):
                return await call_next(request)

        space_id = resolve_espacio_id_for_path(path)
        if not space_id:
            return await call_next(request)

        user_id = request.session.get("user_id")
        if user_id is None:
            return await call_next(request)

        user = get_user_by_id(int(user_id))
        if not user or int(user.get("active") or 0) != 1:
            return await call_next(request)

        access = espacio_access_for_user(user, space_id)
        if access == "ok":
            return await call_next(request)
        if access == "obras":
            return RedirectResponse(f"/espacios/en-obras/{space_id}", status_code=303)
        return RedirectResponse("/portal", status_code=303)


app.add_middleware(EspaciosVisibilityMiddleware)


_PORTAL_WELCOME_EXEMPT_PREFIXES = (
    "/login",
    "/logout",
    "/first-login",
    "/register-first",
    "/portal/bienvenida",
    "/static",
    "/docs",
    "/redoc",
    "/openapi.json",
)


class PortalWelcomeMiddleware(BaseHTTPMiddleware):
    """Obliga a leer la bienvenida en el primer acceso al portal."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        exempt = False
        for prefix in _PORTAL_WELCOME_EXEMPT_PREFIXES:
            if path == prefix or path.startswith(prefix.rstrip("/") + "/"):
                exempt = True
                break
        if exempt:
            return await call_next(request)

        user_id = request.session.get("user_id")
        if user_id is None:
            return await call_next(request)

        if request.session.get("portal_welcome_ok"):
            return await call_next(request)

        if _session_user_is_invitado(request):
            request.session["portal_welcome_ok"] = True
            return await call_next(request)

        if has_accepted_portal_welcome(user_id=int(user_id)):
            request.session["portal_welcome_ok"] = True
            return await call_next(request)

        return RedirectResponse("/portal/bienvenida", status_code=303)


app.add_middleware(PortalWelcomeMiddleware)


class EnforceActiveUserMiddleware(BaseHTTPMiddleware):
    """Si el admin desactiva al usuario, la cookie de sesión deja de valer en la siguiente petición."""

    async def dispatch(self, request: Request, call_next):
        user_id = request.session.get("user_id")
        if user_id is not None:
            user = get_user_by_id(int(user_id))
            if not user or int(user.get("active") or 0) != 1:
                request.session.clear()
        return await call_next(request)


# Extensiones bajo /static que exigen sesión (CSS/logo siguen públicos para /login).
_STATIC_PROTECTED_SUFFIXES = (
    ".pdf",
    ".xlsx",
    ".xls",
    ".docx",
    ".doc",
    ".odt",
    ".ods",
)


class ProtectStaticDocumentsMiddleware(BaseHTTPMiddleware):
    """Impide descargar documentos de /static sin sesión de usuario activo."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""
        if path.startswith("/static/"):
            lower = path.lower()
            if any(lower.endswith(suf) for suf in _STATIC_PROTECTED_SUFFIXES):
                user_id = request.session.get("user_id")
                if not user_id:
                    accept = (request.headers.get("accept") or "").lower()
                    if "text/html" in accept:
                        return RedirectResponse("/login", status_code=303)
                    return JSONResponse(
                        {"detail": "No autenticado"},
                        status_code=401,
                    )
                user = get_user_by_id(int(user_id))
                if not user or int(user.get("active") or 0) != 1:
                    request.session.clear()
                    accept = (request.headers.get("accept") or "").lower()
                    if "text/html" in accept:
                        return RedirectResponse("/login", status_code=303)
                    return JSONResponse(
                        {"detail": "Sesión inválida"},
                        status_code=401,
                    )
        return await call_next(request)


_INVITADO_MUTATE_ALLOWED = frozenset(
    {
        "/login",
        "/logout",
        "/first-login",
        "/register-first",
    }
)


class InvitadoReadOnlyMiddleware(BaseHTTPMiddleware):
    """El rol invitado puede consultar el portal pero no persiste cambios en Neon."""

    async def dispatch(self, request: Request, call_next):
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)
        path = request.url.path or ""
        if path in _INVITADO_MUTATE_ALLOWED:
            return await call_next(request)
        if path.startswith("/portal/avisos/") and path.endswith("/ok"):
            return await call_next(request)
        if not _session_user_is_invitado(request):
            return await call_next(request)
        accept = (request.headers.get("accept") or "").lower()
        if "text/html" in accept:
            return HTMLResponse(
                "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
                "<title>Solo lectura</title></head><body style='font-family:sans-serif;padding:2rem'>"
                "<p>El rol Invitado es de solo lectura: no se pueden guardar cambios.</p>"
                "<p><a href='/portal'>Volver al portal</a></p>"
                "</body></html>",
                status_code=403,
            )
        return JSONResponse(
            {"detail": "El rol Invitado es de solo lectura."},
            status_code=403,
        )


app.add_middleware(EnforceActiveUserMiddleware)
# Debe ir dentro de SessionMiddleware (añadir antes) para leer request.session.
app.add_middleware(InvitadoReadOnlyMiddleware)
app.add_middleware(ProtectStaticDocumentsMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="campus_portal_session",
    max_age=60 * 60,  # 1 hora sin actividad
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
    str(BASE_DIR / "consultas" / "jefatura" / "templates"),
    str(BASE_DIR / "consultas" / "novedades_alumnos" / "templates"),
    str(BASE_DIR / "publicar_avisos" / "templates"),
    str(BASE_DIR / "competencias" / "templates"),
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
    headers = getattr(exc, "headers", None)
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

    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=headers)


app.include_router(login_router)
app.include_router(register_first_router)
app.include_router(first_login_router)
app.include_router(portal_welcome_router)
app.include_router(portal_router)
app.include_router(espacios_obras_router)
app.include_router(admin_espacios_visibles_router)
app.include_router(admin_sanciones_router)
app.include_router(listados_router)
app.include_router(cuaderno_router)
app.include_router(documentos_router)
app.include_router(documentos_jefatura_router)
app.include_router(novedades_alumnos_router)
app.include_router(change_password_router)
app.include_router(ausencias_router)
app.include_router(reservas_router)
app.include_router(moscosos_reservar_router)
app.include_router(moscosos_staff_router)
app.include_router(moscosos_router)
app.include_router(extraescolares_router)
app.include_router(publicar_avisos_router)
app.include_router(competencias_router)
app.include_router(buzones_router)

app.include_router(admin_school_calendar_router)

for _stem in ADMIN_ROUTERS:
    _router = load_admin_router(_stem)
    app.include_router(_router)
    print(
        f"[admin] {_stem} registrado -> {_router.prefix or '-'} ({len(_router.routes)} rutas)",
        flush=True,
    )

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

