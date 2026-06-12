"""Dependencias de acceso a la app Moscosos (portal autenticado + permiso)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from auth import load_user_dep
from utils.enums import PERM_MOSCOSOS_APP, PERM_MOSCOSOS_STAFF
from utils.permissions import has_permission


def require_moscosos_access(
    request: Request,
    user: dict = Depends(load_user_dep),
) -> dict:
    """
    Usuario autenticado en el portal, activo y con rol que puede usar Moscosos.
    Sin sesión → 401 (login). Sin permiso o inactivo → 403 (portal).
    """
    if user.get("active") != 1:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Usuario inactivo")

    if not has_permission(user, PERM_MOSCOSOS_APP):
        raise HTTPException(status_code=403, detail="Sin permiso para Moscosos")

    return user


def require_moscosos_staff(
    user: dict = Depends(require_moscosos_access),
) -> dict:
    """Secciones de gestión Moscosos: admin, jefe, director y secretario."""
    if not has_permission(user, PERM_MOSCOSOS_STAFF):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para esta sección de Moscosos",
        )
    return user
