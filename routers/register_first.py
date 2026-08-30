from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from context import ctx
from db.users import create_first_admin, has_any_user
from security.password_policy import PASSWORD_POLICY_HINT, validate_password

router = APIRouter()


@router.get("/register-first-admin")
def register_first_admin_alias():
    return RedirectResponse("/register-first", status_code=301)


@router.get("/register-first", response_class=HTMLResponse)
def register_first_form(request: Request):
    if has_any_user():
        return RedirectResponse("/login", status_code=303)

    return request.app.state.templates.TemplateResponse(
        "register_first.html",
        ctx(
            request,
            user=None,
            title="Crear administrador",
            hide_chrome=True,
            password_policy_hint=PASSWORD_POLICY_HINT,
        ),
    )


@router.post("/register-first")
def register_first_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    if has_any_user():
        return RedirectResponse("/login", status_code=303)

    form_ctx = {
        "request": request,
        "user": None,
        "title": "Crear administrador",
        "hide_chrome": True,
        "password_policy_hint": PASSWORD_POLICY_HINT,
    }

    policy_error = validate_password(
        password,
        name=name.strip(),
        email=email.strip(),
    )
    if policy_error:
        return request.app.state.templates.TemplateResponse(
            "register_first.html",
            ctx(**form_ctx, error=policy_error),
        )

    create_first_admin(name=name, email=email, password=password)
    return RedirectResponse("/login", status_code=303)
