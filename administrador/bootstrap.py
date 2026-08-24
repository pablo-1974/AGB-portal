"""Carga routers de administración desde ``administrador/routers/``."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROUTERS = PROJECT_ROOT / "administrador" / "routers"

_log = logging.getLogger(__name__)

ADMIN_ROUTERS = (
    "admin_users",
    "admin_students",
    "admin_dashboard",
    "backup",
    "admin_groups",
    "admin_schedules",
    "admin_departamentos",
    "admin_subject_catalog",
    "admin_enrolled_subjects",
    "admin_moscosos_calendar",
)


def load_router(stem: str):
    """Carga un router admin desde su .py en ``administrador/routers/``."""
    path = LOCAL_ROUTERS / f"{stem}.py"
    if not path.is_file():
        raise FileNotFoundError(f"No hay router «{stem}» en administrador/routers ({path})")
    mod_name = f"administrador.routers.{stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Sin loader para {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    router = getattr(mod, "router", None)
    if router is None:
        raise AttributeError(f"{path} no define «router»")
    if not getattr(router, "routes", None):
        raise RuntimeError(f"Router «{stem}» en {path} no tiene rutas")
    prefix = getattr(router, "prefix", "")
    _log.info("Router admin cargado: %s (%s, %d rutas)", stem, prefix or "—", len(router.routes))
    return router
