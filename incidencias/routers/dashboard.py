# routers/dashboard.py

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from auth import load_user_dep

router = APIRouter()


@router.get("/dashboard")
def dashboard_entry(user: dict = Depends(load_user_dep)):
    """
    Punto de entrada general al dashboard.
    Redirige según rol.
    """

    # Admin / Jefatura / Dirección
    if user["role"] in ("admin", "jefe", "director", "secretario"):
        return RedirectResponse("/admin/dashboard", status_code=303)

    # Convivencia
    if user["role"] == "convivencia":
        return RedirectResponse("/convivencia/dashboard", status_code=303)

    # Profesor / Orientador (temporalmente)
    if user["role"] in ("profesor", "orientador", "extraescolares"):
        return RedirectResponse("/profesor/dashboard", status_code=303)

    # Fallback seguro
    return RedirectResponse("/login", status_code=303)
