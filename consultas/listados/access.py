"""Permisos de la app Listados."""

from __future__ import annotations

from utils.enums import ROLE_ADMIN, ROLES_ADMINISTRATIVOS, ROLES_TODOS


def role_key(user: dict | None) -> str:
    return str((user or {}).get("role") or "").strip().lower()


def is_portal_role(user: dict | None) -> bool:
    """Cualquier rol del portal (incluye profesor, orientador, convivencia y administración)."""
    return role_key(user) in ROLES_TODOS


def is_listados_staff(user: dict | None) -> bool:
    """Personal administrativo (admin, jefe, director, secretario)."""
    return role_key(user) in ROLES_ADMINISTRATIVOS


def can_access_profesores(user: dict | None) -> bool:
    return is_portal_role(user)


def can_access_alumnos(user: dict | None) -> bool:
    return is_portal_role(user)


def can_access_horarios(user: dict | None) -> bool:
    return is_portal_role(user)


def can_access_asignaturas(user: dict | None) -> bool:
    """Pruebas: solo admin; ampliar permisos cuando se abra el listado."""
    return role_key(user) == ROLE_ADMIN


def can_profesorado_tab(user: dict | None) -> bool:
    return is_listados_staff(user)


def can_horarios_view(user: dict | None, view: str) -> bool:
    v = (view or "grupos").strip().lower()
    if v == "grupos":
        return is_portal_role(user)
    if v in ("profesores", "aulas", "guardias"):
        return is_listados_staff(user)
    return False
