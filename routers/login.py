from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from context import ctx
from db.users import get_user_by_email, has_any_user, update_last_login
from security.passwords import verify_password

router = APIRouter()


def _login_template_ctx(request: Request, **extra):
    return ctx(
        request,
        user=None,
        title="Acceso",
        hide_chrome=True,
        show_register_first_link=not has_any_user(),
        **extra,
    )


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return request.app.state.templates.TemplateResponse(
        "login.html",
        _login_template_ctx(request),
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    user = get_user_by_email(email)

    if not user:
        return request.app.state.templates.TemplateResponse(
            "login.html",
            _login_template_ctx(
                request,
                error="Credenciales incorrectas",
                email=email,
            ),
        )

    if user["active"] != 1:
        return request.app.state.templates.TemplateResponse(
            "login.html",
            _login_template_ctx(
                request,
                error="El usuario está desactivado. Contacta con un administrador.",
                email=email,
            ),
        )

    if user["password_hash"] is None or user.get("must_change_password"):
        request.session.clear()
        request.session["first_login_user_id"] = user["id"]
        return RedirectResponse(url="/first-login", status_code=303)

    if not verify_password(password, user["password_hash"]):
        return request.app.state.templates.TemplateResponse(
            "login.html",
            _login_template_ctx(
                request,
                error="Credenciales incorrectas",
                email=email,
            ),
        )

    request.session.clear()
    request.session["user_id"] = user["id"]
    update_last_login(user_id=user["id"])

    return RedirectResponse(url="/portal", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
