import os
import hashlib
import hmac
import base64

_HASH_NAME = "sha256"
_ITERATIONS = 260_000
_SALT_SIZE = 16


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("La contraseña no puede estar vacía")

    salt = os.urandom(_SALT_SIZE)

    dk = hashlib.pbkdf2_hmac(
        _HASH_NAME,
        password.encode("utf-8"),
        salt,
        _ITERATIONS,
    )

    salt_b64 = base64.b64encode(salt).decode("utf-8")
    hash_b64 = base64.b64encode(dk).decode("utf-8")

    return f"{_ITERATIONS}${salt_b64}${hash_b64}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        iterations_str, salt_b64, hash_b64 = stored_hash.split("$")
        iterations = int(iterations_str)

        salt = base64.b64decode(salt_b64)
        stored_dk = base64.b64decode(hash_b64)

        new_dk = hashlib.pbkdf2_hmac(
            _HASH_NAME,
            password.encode("utf-8"),
            salt,
            iterations,
        )

        return hmac.compare_digest(new_dk, stored_dk)

    except Exception:
        return False
