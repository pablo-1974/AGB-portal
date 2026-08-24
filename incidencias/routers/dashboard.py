# routers/dashboard.py

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from auth import load_user_dep
from utils.enums import (
    ROLE_ADMIN,
    ROLE_CONVIVENCIA,
    ROLE_DIRECTOR,
    ROLE_EXTRAESCOLARES,
    ROLE_INVITADO,
    ROLE_JEFE,
    ROLE_ORIENTADOR,
    ROLE_PROFESOR,
    ROLE_SECRETARIO,
)

router = APIRouter()


@router.get("/dashboard")
def dashboard_entry(user: dict = Depends(load_user_dep)):
    """
    Punto de entrada general al dashboard.
    Redirige según rol.
    """
    role = str(user.get("role") or "").strip().lower()

    # Admin / Jefatura / Dirección / Invitado (inspección, solo lectura)
    if role in (ROLE_ADMIN, ROLE_JEFE, ROLE_DIRECTOR, ROLE_SECRETARIO, ROLE_INVITADO):
        return RedirectResponse("/admin/dashboard", status_code=303)

    # Convivencia
    if role == ROLE_CONVIVENCIA:
        return RedirectResponse("/convivencia/dashboard", status_code=303)

    # Profesor / Orientador / Extraescolares
    if role in (ROLE_PROFESOR, ROLE_ORIENTADOR, ROLE_EXTRAESCOLARES):
        return RedirectResponse("/profesor/dashboard", status_code=303)

    return RedirectResponse("/portal", status_code=303)
