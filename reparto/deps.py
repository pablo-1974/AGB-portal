"""Dependencias de acceso a Reparto (equipo directivo)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from auth import load_user_dep
from utils.enums import PERM_REPARTO_APP
from utils.permissions import has_permission


def require_reparto_access(
    request: Request,
    user: dict = Depends(load_user_dep),
) -> dict:
    if user.get("active") != 1:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Usuario inactivo")
    if not has_permission(user, PERM_REPARTO_APP):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para Reparto",
        )
    return user
