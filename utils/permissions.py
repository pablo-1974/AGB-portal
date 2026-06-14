from utils.enums import (
    PERM_LISTADOS_ALUMNOS,
    PERM_LISTADOS_APP,
    PERM_LISTADOS_HORARIOS,
    PERM_LISTADOS_PROFESORES,
    PERMISSIONS_BY_ROLE,
    ROLES_TODOS,
)

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

    allowed = PERMISSIONS_BY_ROLE.get(permission)
    if not allowed:
        if permission in _LISTADOS_ALL_ROLES:
            allowed = ROLES_TODOS
        else:
            return False
    return role in allowed
