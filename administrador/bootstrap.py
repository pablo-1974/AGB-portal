"""Carga routers de administración desde ``administrador/routers/``."""

from __future__ import annotations

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROUTERS = PROJECT_ROOT / "administrador" / "routers"

ADMIN_ROUTERS = (
    "admin_users",
    "admin_students",
    "admin_dashboard",
    "backup",
    "admin_groups",
    "admin_schedules",
    "admin_enrolled_subjects",
    "admin_subject_catalog",
    "admin_moscosos_calendar",
)


def load_router(stem: str):
    path = LOCAL_ROUTERS / f"{stem}.py"
    if not path.is_file():
        raise FileNotFoundError(f"No hay router '{stem}' en administrador/routers")
    mod_name = f"administrador.router.{stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    loader = spec.loader
    if loader is None:
        raise RuntimeError(f"Sin loader para {path}")
    loader.exec_module(mod)
    return mod.router
