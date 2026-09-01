"""Política unificada de contraseñas del portal."""

from __future__ import annotations

import re

MIN_PASSWORD_LENGTH = 10

PASSWORD_POLICY_HINT = (
    "Mínimo 10 caracteres, con mayúscula, minúscula, dígito y símbolo. "
    "No puede incluir tu nombre ni tu email."
)


def validate_password(
    password: str,
    *,
    name: str = "",
    email: str = "",
) -> str | None:
    """Devuelve mensaje de error o None si la contraseña cumple la política."""
    pw = password or ""
    if len(pw) < MIN_PASSWORD_LENGTH:
        return f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres."
    if not re.search(r"[A-ZÁÉÍÓÚÜÑ]", pw):
        return "La contraseña debe incluir al menos una letra mayúscula."
    if not re.search(r"[a-záéíóúüñ]", pw):
        return "La contraseña debe incluir al menos una letra minúscula."
    if not re.search(r"\d", pw):
        return "La contraseña debe incluir al menos un dígito."
    if not re.search(r"[^\w\s]", pw):
        return "La contraseña debe incluir al menos un símbolo."
    if _contains_identity(pw, name=name, email=email):
        return "La contraseña no puede incluir tu nombre ni tu email."
    return None


def _contains_identity(password: str, *, name: str, email: str) -> bool:
    pw_fold = password.casefold()
    email_fold = (email or "").strip().casefold()
    if email_fold and email_fold in pw_fold:
        return True
    if email_fold and "@" in email_fold:
        local = email_fold.split("@", 1)[0]
        if len(local) >= 3 and local in pw_fold:
            return True
    name_fold = (name or "").strip().casefold()
    if len(name_fold) >= 3 and name_fold in pw_fold:
        return True
    for token in re.findall(r"\w+", name_fold):
        if len(token) >= 3 and token in pw_fold:
            return True
    return False
