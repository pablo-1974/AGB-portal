"""Añade pydeps al sys.path para paquetes locales (Avast corrompe site-packages)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / "pydeps"


def ensure_local_deps() -> None:
    if DEPS.is_dir():
        path = str(DEPS)
        if path not in sys.path:
            sys.path.insert(0, path)
