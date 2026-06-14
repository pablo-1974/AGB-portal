from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from context import ctx
from db.users import create_first_admin, has_any_user

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

    if len(password) < 8:
        return request.app.state.templates.TemplateResponse(
            "register_first.html",
            ctx(
                request,
                user=None,
                title="Crear administrador",
                hide_chrome=True,
                error="La contraseña debe tener al menos 8 caracteres.",
            ),
        )

    create_first_admin(name=name, email=email, password=password)
    return RedirectResponse("/login", status_code=303)
