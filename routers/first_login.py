from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from context import ctx
from db.users import get_user_by_id, set_user_password
from security.passwords import hash_password

router = APIRouter()


@router.get("/first-login", response_class=HTMLResponse)
def first_login_form(request: Request):
    user_id = request.session.get("first_login_user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    user = get_user_by_id(user_id)
    if not user or user["active"] != 1:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    return request.app.state.templates.TemplateResponse(
        "first_login.html",
        ctx(request, user=None, title="Definir contraseña", hide_chrome=True),
    )


@router.post("/first-login", response_class=HTMLResponse)
def first_login_submit(
    request: Request,
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    user_id = request.session.get("first_login_user_id")
    if not user_id:
        return RedirectResponse("/login", status_code=303)

    user = get_user_by_id(user_id)
    if not user or user["active"] != 1:
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    if password != password_confirm:
        return request.app.state.templates.TemplateResponse(
            "first_login.html",
            ctx(
                request,
                user=None,
                title="Definir contraseña",
                hide_chrome=True,
                error="Las contraseñas no coinciden.",
            ),
        )

    if len(password) < 8:
        return request.app.state.templates.TemplateResponse(
            "first_login.html",
            ctx(
                request,
                user=None,
                title="Definir contraseña",
                hide_chrome=True,
                error="La contraseña debe tener al menos 8 caracteres.",
            ),
        )

    password_hash = hash_password(password)
    set_user_password(user_id=user_id, password_hash=password_hash)

    request.session.clear()
    request.session["user_id"] = user_id

    return RedirectResponse("/portal", status_code=303)
