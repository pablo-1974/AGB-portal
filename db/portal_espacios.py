"""Visibilidad de espacios del portal (visible / en obras / no visible)."""

from __future__ import annotations

from db.connection import get_db

TABLE = "portal_espacio_visibility"

STATUS_VISIBLE = "visible"
STATUS_OBRAS = "obras"
STATUS_HIDDEN = "hidden"
STATUSES = frozenset({STATUS_VISIBLE, STATUS_OBRAS, STATUS_HIDDEN})

# Catálogo fijo: Consultas → Apps → Buzones (mismo orden que /portal).
PORTAL_ESPACIOS: tuple[dict[str, str], ...] = (
    {
        "id": "cuaderno",
        "title": "📖 Cuaderno del profesor",
        "section": "Consultas",
        "border": "border-indigo-300",
        "href": "/cuaderno/",
    },
    {
        "id": "documentos",
        "title": "📄 Documentos institucionales",
        "section": "Consultas",
        "border": "border-indigo-300",
        "href": "/documentos/",
    },
    {
        "id": "documentos-jefatura",
        "title": "🗂️ Documentos Jefatura",
        "section": "Consultas",
        "border": "border-indigo-300",
        "href": "/documentos-jefatura/",
    },
    {
        "id": "listados",
        "title": "📇 Listados",
        "section": "Consultas",
        "border": "border-indigo-300",
        "href": "/listados/",
    },
    {
        "id": "novedades-alumnos",
        "title": "🆕 Novedades alumnos",
        "section": "Consultas",
        "border": "border-indigo-300",
        "href": "/novedades-alumnos/",
    },
    {
        "id": "calendario-extraescolares",
        "title": "📅 Calendario extraescolares",
        "section": "Consultas",
        "border": "border-indigo-300",
        "href": "/extraescolares/calendario",
    },
    {
        "id": "incidencias",
        "title": "📝 Incidencias",
        "section": "Apps",
        "border": "border-teal-300",
        "href": "/dashboard",
    },
    {
        "id": "reservas",
        "title": "📅 Reserva de aulas",
        "section": "Apps",
        "border": "border-teal-300",
        "href": "/reservas/dashboard",
    },
    {
        "id": "ausencias",
        "title": "📋 Ausencias",
        "section": "Apps",
        "border": "border-teal-300",
        "href": "/ausencias/dashboard",
    },
    {
        "id": "publicar-avisos",
        "title": "📢 Publicar avisos",
        "section": "Apps",
        "border": "border-teal-300",
        "href": "/publicar-avisos/",
    },
    {
        "id": "moscosos",
        "title": "🎯 Moscosos",
        "section": "Apps",
        "border": "border-teal-300",
        "href": "/moscosos/dashboard",
    },
    {
        "id": "extraescolares",
        "title": "🏃 Actividades extraescolares",
        "section": "Apps",
        "border": "border-teal-300",
        "href": "/extraescolares/dashboard",
    },
    {
        "id": "competencias",
        "title": "📊 Evaluación de competencias",
        "section": "Apps",
        "border": "border-teal-300",
        "href": "/competencias/dashboard",
    },
    {
        "id": "buzones-funcionamiento",
        "title": "📬 Funcionamiento del portal",
        "section": "Buzones",
        "border": "border-amber-300",
        "href": "/buzones/funcionamiento-portal",
    },
    {
        "id": "buzones-mantenimiento",
        "title": "🔧 Mantenimiento",
        "section": "Buzones",
        "border": "border-amber-300",
        "href": "/buzones/mantenimiento",
    },
    {
        "id": "buzones-listados",
        "title": "📇 Listados (buzón)",
        "section": "Buzones",
        "border": "border-amber-300",
        "href": "/buzones/listados",
    },
)

_DEFAULT_STATUS: dict[str, str] = {
    e["id"]: STATUS_HIDDEN if e["id"] == "competencias" else STATUS_VISIBLE
    for e in PORTAL_ESPACIOS
}

_VALID_IDS = frozenset(_DEFAULT_STATUS)
_ESPACIO_BY_ID = {e["id"]: e for e in PORTAL_ESPACIOS}

_schema_ready = False
_status_cache: dict[str, str] | None = None


def ensure_portal_espacios_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    space_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL
                        CHECK (status IN ('visible', 'obras', 'hidden')),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
    _schema_ready = True


def invalidate_espacios_cache() -> None:
    global _status_cache
    _status_cache = None


def get_espacio(space_id: str) -> dict[str, str] | None:
    return _ESPACIO_BY_ID.get(space_id)


def get_espacios_statuses(*, use_cache: bool = True) -> dict[str, str]:
    """Devuelve status por space_id (defaults + filas en BD)."""
    global _status_cache
    if use_cache and _status_cache is not None:
        return dict(_status_cache)

    ensure_portal_espacios_schema()
    statuses = dict(_DEFAULT_STATUS)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT space_id, status FROM {TABLE}")
            for row in cur.fetchall():
                sid = str(row["space_id"] or "").strip()
                st = str(row["status"] or "").strip()
                if sid in _VALID_IDS and st in STATUSES:
                    statuses[sid] = st

    _status_cache = dict(statuses)
    return statuses


def get_espacio_status(space_id: str) -> str:
    return get_espacios_statuses().get(space_id, STATUS_VISIBLE)


def save_espacios_statuses(updates: dict[str, str]) -> list[tuple[str, str, str]]:
    """Persiste status válidos y limpia la caché.

    Devuelve ``(space_id, old_status, new_status)`` solo cuando el valor cambia.
    """
    ensure_portal_espacios_schema()
    rows: list[tuple[str, str]] = []
    for sid, st in updates.items():
        sid_c = str(sid or "").strip()
        st_c = str(st or "").strip()
        if sid_c in _VALID_IDS and st_c in STATUSES:
            rows.append((sid_c, st_c))
    if not rows:
        return []

    transitions: list[tuple[str, str, str]] = []
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT space_id, status FROM {TABLE}")
            db_map = {
                str(r["space_id"] or "").strip(): str(r["status"] or "").strip()
                for r in cur.fetchall()
            }
            for sid, st in rows:
                old = db_map.get(sid) or _DEFAULT_STATUS.get(sid, STATUS_VISIBLE)
                if old not in STATUSES:
                    old = _DEFAULT_STATUS.get(sid, STATUS_VISIBLE)
                if old != st:
                    transitions.append((sid, old, st))
                cur.execute(
                    f"""
                    INSERT INTO {TABLE} (space_id, status, updated_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (space_id) DO UPDATE
                    SET status = EXCLUDED.status,
                        updated_at = now()
                    """,
                    (sid, st),
                )
    invalidate_espacios_cache()
    return transitions


def _path_matches(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def resolve_espacio_id_for_path(path: str) -> str | None:
    """Asocia una ruta HTTP a un espacio del portal (o None)."""
    p = (path or "").rstrip("/") or "/"
    # Más específico primero
    if _path_matches(p, "/extraescolares/calendario") or p == "/extraescolares/calendario":
        return "calendario-extraescolares"
    if _path_matches(p, "/cuaderno"):
        return "cuaderno"
    if _path_matches(p, "/documentos-jefatura"):
        return "documentos-jefatura"
    if _path_matches(p, "/documentos"):
        return "documentos"
    if _path_matches(p, "/listados"):
        return "listados"
    if _path_matches(p, "/novedades-alumnos"):
        return "novedades-alumnos"
    if _path_matches(p, "/reservas"):
        return "reservas"
    if _path_matches(p, "/ausencias"):
        return "ausencias"
    if _path_matches(p, "/publicar-avisos"):
        return "publicar-avisos"
    if _path_matches(p, "/moscosos"):
        return "moscosos"
    if _path_matches(p, "/extraescolares"):
        return "extraescolares"
    if _path_matches(p, "/competencias"):
        return "competencias"
    if _path_matches(p, "/buzones/funcionamiento-portal"):
        return "buzones-funcionamiento"
    if _path_matches(p, "/buzones/mantenimiento"):
        return "buzones-mantenimiento"
    if _path_matches(p, "/buzones/listados"):
        return "buzones-listados"
    # Incidencias (sin prefijo único)
    if _is_incidencias_path(p):
        return "incidencias"
    return None


def _is_incidencias_path(path: str) -> bool:
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
        if _path_matches(path, prefix):
            return True
    if _path_matches(path, "/admin/dashboard"):
        return True
    if _path_matches(path, "/dashboard"):
        return True
    return False


def portal_card_visible(user: dict | None, space_id: str, status: str | None = None) -> bool:
    """Si la tarjeta debe mostrarse en /portal (permisos aparte)."""
    st = status if status is not None else get_espacio_status(space_id)
    role = str((user or {}).get("role") or "").strip().lower()
    if role in {"admin", "invitado"}:
        return True
    return st != STATUS_HIDDEN


def espacio_access_for_user(user: dict | None, space_id: str) -> str:
    """
    Resultado de acceso a la app:
    - ``ok``: entrar normal
    - ``obras``: página en obras
    - ``forbidden``: no visible (solo admin)
    """
    role = str((user or {}).get("role") or "").strip().lower()
    if role in {"admin", "invitado"}:
        return "ok"
    st = get_espacio_status(space_id)
    if st == STATUS_HIDDEN:
        return "forbidden"
    if st == STATUS_OBRAS:
        return "obras"
    return "ok"
