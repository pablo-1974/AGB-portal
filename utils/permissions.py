from utils.enums import (
    PERM_LISTADOS_ALUMNOS,
    PERM_LISTADOS_APP,
    PERM_LISTADOS_HORARIOS,
    PERM_LISTADOS_PROFESORES,
    PERMISSIONS_BY_ROLE,
    ROLE_INVITADO,
    ROLES_TODOS,
)


def is_invitado(user: dict | None) -> bool:
    if not user:
        return False
    return str(user.get("role") or "").strip().lower() == ROLE_INVITADO

# Listados: acceso base para todos los roles (fallback si el servidor no recargó enums).
_LISTADOS_ALL_ROLES = frozenset(
    {
        PERM_LISTADOS_APP,
        PERM_LISTADOS_PROFESORES,
        PERM_LISTADOS_ALUMNOS,
        PERM_LISTADOS_HORARIOS,
    }
)


def has_permission(user: dict | None, permission: str) -> bool:
    if not user:
        return False

    role = str(user.get("role") or "").strip().lower()
    if not role:
        return False
    if role == ROLE_INVITADO:
        return True

    allowed = PERMISSIONS_BY_ROLE.get(permission)
    if not allowed:
        if permission in _LISTADOS_ALL_ROLES:
            allowed = ROLES_TODOS
        else:
            return False
    return role in allowed
