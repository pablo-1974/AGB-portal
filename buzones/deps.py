"""Dependencias de acceso a los buzones."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from auth import load_user_dep
from utils.enums import (
    PERM_BUZONES_LISTAR,
    PERM_BUZONES_MARCAR_LEIDO,
    PERM_BUZONES_MARCAR_LEIDO_MANTENIMIENTO,
    PERM_BUZONES_LISTAR_LISTADOS,
    PERM_BUZONES_MARCAR_LEIDO_LISTADOS,
)
from utils.permissions import has_permission


def require_buzones_user(
    request: Request,
    user: dict = Depends(load_user_dep),
) -> dict:
    if user.get("active") != 1:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Usuario inactivo")
    return user


def require_buzones_staff(
    user: dict = Depends(require_buzones_user),
) -> dict:
    if not has_permission(user, PERM_BUZONES_LISTAR):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para listar mensajes",
        )
    return user


def require_funcionamiento_marcar(
    user: dict = Depends(require_buzones_user),
) -> dict:
    if not has_permission(user, PERM_BUZONES_MARCAR_LEIDO):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para marcar mensajes como leídos",
        )
    return user


def require_mantenimiento_marcar(
    user: dict = Depends(require_buzones_user),
) -> dict:
    if not has_permission(user, PERM_BUZONES_MARCAR_LEIDO_MANTENIMIENTO):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para marcar mensajes como leídos",
        )
    return user


def require_listados_buzon_staff(
    user: dict = Depends(require_buzones_user),
) -> dict:
    if not has_permission(user, PERM_BUZONES_LISTAR_LISTADOS):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para listar mensajes del buzón de listados",
        )
    return user


def require_listados_buzon_marcar(
    user: dict = Depends(require_buzones_user),
) -> dict:
    if not has_permission(user, PERM_BUZONES_MARCAR_LEIDO_LISTADOS):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para marcar mensajes como leídos",
        )
    return user
