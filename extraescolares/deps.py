"""Dependencias de acceso a Actividades extraescolares."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from auth import load_user_dep
from utils.enums import (
    PERM_EXTRAESCOLARES_APP,
    PERM_EXTRAESCOLARES_DELETE,
    PERM_EXTRAESCOLARES_EDIT_CONFIRMED,
    PERM_EXTRAESCOLARES_LISTADO,
)
from utils.permissions import has_permission


def require_extraescolares_access(
    request: Request,
    user: dict = Depends(load_user_dep),
) -> dict:
    if user.get("active") != 1:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Usuario inactivo")
    if not has_permission(user, PERM_EXTRAESCOLARES_APP):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para Actividades extraescolares",
        )
    return user


def require_extraescolares_edit_confirmed(
    request: Request,
    user: dict = Depends(require_extraescolares_access),
) -> dict:
    if not has_permission(user, PERM_EXTRAESCOLARES_EDIT_CONFIRMED):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para editar actividades confirmadas",
        )
    return user


def require_extraescolares_listado(
    request: Request,
    user: dict = Depends(require_extraescolares_access),
) -> dict:
    if not has_permission(user, PERM_EXTRAESCOLARES_LISTADO):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para consultar el listado de actividades",
        )
    return user


def require_extraescolares_delete(
    request: Request,
    user: dict = Depends(require_extraescolares_access),
) -> dict:
    if not has_permission(user, PERM_EXTRAESCOLARES_DELETE):
        raise HTTPException(
            status_code=403,
            detail="Sin permiso para eliminar actividades extraescolares",
        )
    return user
