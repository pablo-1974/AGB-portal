"""Permisos de la app Listados."""

from __future__ import annotations

from utils.enums import (
    PERM_LISTADOS_ALUMNOS,
    PERM_LISTADOS_APP,
    PERM_LISTADOS_HORARIOS,
    PERM_LISTADOS_HORARIOS_AULAS,
    PERM_LISTADOS_HORARIOS_GUARDIAS,
    PERM_LISTADOS_HORARIOS_PROFESORES,
    PERM_LISTADOS_PROFESORES,
    PERM_LISTADOS_PROFESORADO_TAB,
    ROLES_TODOS,
)
from utils.permissions import has_permission


def role_key(user: dict | None) -> str:
    return str((user or {}).get("role") or "").strip().lower()


def is_portal_role(user: dict | None) -> bool:
    """Cualquier rol del portal (incluye profesor, orientador, convivencia y administración)."""
    return role_key(user) in ROLES_TODOS


def is_listados_staff(user: dict | None) -> bool:
    """Pestañas staff de listados (administración; invitado solo si tiene el permiso)."""
    return has_permission(user, PERM_LISTADOS_PROFESORADO_TAB)


def can_access_app(user: dict | None) -> bool:
    return has_permission(user, PERM_LISTADOS_APP)


def can_access_profesores(user: dict | None) -> bool:
    return has_permission(user, PERM_LISTADOS_PROFESORES)


def can_access_alumnos(user: dict | None) -> bool:
    return has_permission(user, PERM_LISTADOS_ALUMNOS)


def can_access_horarios(user: dict | None) -> bool:
    return has_permission(user, PERM_LISTADOS_HORARIOS)


def can_access_asignaturas(user: dict | None) -> bool:
    """Consulta de asignaturas matriculadas: quienes tienen la app Listados."""
    return has_permission(user, PERM_LISTADOS_APP)


def can_profesorado_tab(user: dict | None) -> bool:
    return is_listados_staff(user)


def can_horarios_view(user: dict | None, view: str) -> bool:
    v = (view or "grupos").strip().lower()
    if v == "grupos":
        return is_portal_role(user)
    if v == "profesores":
        return has_permission(user, PERM_LISTADOS_HORARIOS_PROFESORES)
    if v == "aulas":
        return has_permission(user, PERM_LISTADOS_HORARIOS_AULAS)
    if v == "guardias":
        return has_permission(user, PERM_LISTADOS_HORARIOS_GUARDIAS)
    return False
