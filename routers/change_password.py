from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from auth import load_user_dep
from context import ctx
from db.users import set_user_password
from security.passwords import hash_password, verify_password

router = APIRouter()


@router.get("/change-password", response_class=HTMLResponse)
def change_password_view(request: Request, user: dict = Depends(load_user_dep)):
    return request.app.state.templates.TemplateResponse(
        "change_password.html",
        ctx(request, user=user, title="Cambiar contraseña"),
    )


@router.post("/change-password")
def change_password_submit(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: dict = Depends(load_user_dep),
):
    if not user["password_hash"]:
        return request.app.state.templates.TemplateResponse(
            "change_password.html",
            ctx(
                request,
                user=user,
                title="Cambiar contraseña",
                error="Tu cuenta no tiene contraseña definida para este flujo.",
            ),
        )

    if not verify_password(current_password, user["password_hash"]):
        return request.app.state.templates.TemplateResponse(
            "change_password.html",
            ctx(
                request,
                user=user,
                title="Cambiar contraseña",
                error="La contraseña actual no es correcta.",
            ),
        )

    if new_password != confirm_password:
        return request.app.state.templates.TemplateResponse(
            "change_password.html",
            ctx(
                request,
                user=user,
                title="Cambiar contraseña",
                error="La nueva contraseña y la confirmación no coinciden.",
            ),
        )

    if len(new_password) < 6:
        return request.app.state.templates.TemplateResponse(
            "change_password.html",
            ctx(
                request,
                user=user,
                title="Cambiar contraseña",
                error="La nueva contraseña debe tener al menos 6 caracteres.",
            ),
        )

    set_user_password(user_id=user["id"], password_hash=hash_password(new_password))

    return RedirectResponse(url="/portal", status_code=303)
