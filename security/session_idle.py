"""Caducidad de sesión por inactividad (distinta por rol)."""

from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from db.users import get_user_by_id
from utils.enums import ROLES_ADMINISTRATIVOS

SESSION_LAST_KEY = "_session_last_activity"
SESSION_IDLE_DEFAULT_SECONDS = 20 * 60
SESSION_IDLE_DIRECTIVO_SECONDS = 60 * 60
SESSION_COOKIE_MAX_AGE_SECONDS = SESSION_IDLE_DIRECTIVO_SECONDS


def _idle_limit_seconds(role: str | None) -> int:
    r = (role or "").strip().lower()
    if r in ROLES_ADMINISTRATIVOS:
        return SESSION_IDLE_DIRECTIVO_SECONDS
    return SESSION_IDLE_DEFAULT_SECONDS


class SessionIdleTimeoutMiddleware(BaseHTTPMiddleware):
    """Cierra la sesión tras inactividad: 20 min (general) o 60 min (directivos)."""

    async def dispatch(self, request: Request, call_next):
        user_id = request.session.get("user_id")
        first_login_id = request.session.get("first_login_user_id")
        active_uid = user_id or first_login_id

        if active_uid is not None:
            now = time.time()
            last_raw = request.session.get(SESSION_LAST_KEY)
            role: str | None = None
            if user_id is not None:
                user = get_user_by_id(int(user_id))
                if not user or int(user.get("active") or 0) != 1:
                    request.session.clear()
                    return await call_next(request)
                role = str(user.get("role") or "")
            limit = _idle_limit_seconds(role)

            if last_raw is not None:
                try:
                    elapsed = now - float(last_raw)
                except (TypeError, ValueError):
                    elapsed = 0.0
                if elapsed > limit:
                    request.session.clear()
                    return await call_next(request)

            request.session[SESSION_LAST_KEY] = now

        return await call_next(request)
