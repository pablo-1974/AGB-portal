from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse

from db.users import get_user_by_id


def redirect_portal_or_login(request: Request) -> RedirectResponse:
    """Sin permiso: portal con sesión; sin sesión, login. Usado por el manejador HTTP en la app."""
    if request.session.get("user_id"):
        return RedirectResponse("/portal", status_code=303)
    return RedirectResponse("/login", status_code=303)


def load_user_dep(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")

    user = get_user_by_id(user_id)
    if not user:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Sesión inválida")

    return user
