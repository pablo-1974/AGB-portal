from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from context import ctx
from db.login_security import (
    clear_ip_throttle,
    clear_user_login_failures,
    ip_block_remaining_minutes,
    is_user_login_locked,
    log_failed_login_attempt,
    record_ip_login_failure,
    record_user_login_failure,
)
from db.users import get_user_by_email, has_any_user, update_last_login
from utils.permissions import is_invitado
from utils.request_ip import get_client_ip
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
    client_ip = get_client_ip(request)
    email_clean = (email or "").strip()

    block_mins = ip_block_remaining_minutes(client_ip)
    if block_mins is not None:
        return request.app.state.templates.TemplateResponse(
            "login.html",
            _login_template_ctx(
                request,
                error=(
                    f"Demasiados intentos fallidos desde esta conexión. "
                    f"Vuelve a intentarlo en {block_mins} minutos."
                ),
                email=email_clean,
            ),
        )

    user = get_user_by_email(email_clean)

    if not user:
        record_ip_login_failure(client_ip)
        log_failed_login_attempt(
            user_id=None,
            email=email_clean,
            ip_address=client_ip,
            reason="usuario no encontrado",
        )
        return request.app.state.templates.TemplateResponse(
            "login.html",
            _login_template_ctx(
                request,
                error="Credenciales incorrectas",
                email=email_clean,
            ),
        )

    if user["active"] != 1:
        record_ip_login_failure(client_ip)
        log_failed_login_attempt(
            user_id=user["id"],
            email=email_clean,
            ip_address=client_ip,
            reason="usuario desactivado",
        )
        return request.app.state.templates.TemplateResponse(
            "login.html",
            _login_template_ctx(
                request,
                error="El usuario está desactivado. Contacta con un administrador.",
                email=email_clean,
            ),
        )

    if is_user_login_locked(user):
        log_failed_login_attempt(
            user_id=user["id"],
            email=email_clean,
            ip_address=client_ip,
            reason="cuenta bloqueada",
        )
        return request.app.state.templates.TemplateResponse(
            "login.html",
            _login_template_ctx(
                request,
                error=(
                    "Cuenta bloqueada por intentos fallidos. "
                    "Contacta con un administrador."
                ),
                email=email_clean,
            ),
        )

    if user["password_hash"] is None or user.get("must_change_password"):
        request.session.clear()
        request.session["first_login_user_id"] = user["id"]
        return RedirectResponse(url="/first-login", status_code=303)

    if not verify_password(password, user["password_hash"]):
        ip_blocked_mins = record_ip_login_failure(client_ip)
        account_locked = record_user_login_failure(int(user["id"]))
        reason = "contraseña incorrecta"
        if account_locked:
            reason = "contraseña incorrecta; cuenta bloqueada"
        log_failed_login_attempt(
            user_id=user["id"],
            email=email_clean,
            ip_address=client_ip,
            reason=reason,
        )
        if ip_blocked_mins is not None:
            return request.app.state.templates.TemplateResponse(
                "login.html",
                _login_template_ctx(
                    request,
                    error=(
                        f"Demasiados intentos fallidos desde esta conexión. "
                        f"Vuelve a intentarlo en {ip_blocked_mins} minutos."
                    ),
                    email=email_clean,
                ),
            )
        if account_locked:
            return request.app.state.templates.TemplateResponse(
                "login.html",
                _login_template_ctx(
                    request,
                    error=(
                        "Cuenta bloqueada por intentos fallidos. "
                        "Contacta con un administrador."
                    ),
                    email=email_clean,
                ),
            )
        return request.app.state.templates.TemplateResponse(
            "login.html",
            _login_template_ctx(
                request,
                error="Credenciales incorrectas",
                email=email_clean,
            ),
        )

    clear_ip_throttle(client_ip)
    clear_user_login_failures(int(user["id"]))

    request.session.clear()
    request.session["user_id"] = user["id"]
    if not is_invitado(user):
        update_last_login(user_id=user["id"])

    return RedirectResponse(url="/portal", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
