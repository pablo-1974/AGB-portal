"""Carga routers únicamente desde ``incidencias/routers/``."""

from __future__ import annotations

import importlib.util
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ROUTERS = PROJECT_ROOT / "incidencias" / "routers"


def load_router(stem: str):
    path = LOCAL_ROUTERS / f"{stem}.py"
    if not path.is_file():
        raise FileNotFoundError(f"No hay router '{stem}' en incidencias/routers")
    mod_name = f"incidencias.router.{stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    loader = spec.loader
    if loader is None:
        raise RuntimeError(f"Sin loader para {path}")
    loader.exec_module(mod)
    return mod.router
