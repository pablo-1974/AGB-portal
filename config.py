import os
from pathlib import Path


class Settings:
    APP_NAME = "Portal del centro"
    INCIDENCIAS_APP_NAME = os.environ.get("INCIDENCIAS_APP_NAME", "Incidencias del alumnado")
    PORTAL_APP_NAME = os.environ.get("PORTAL_APP_NAME", "Aplicaciones escolares")
    INSTITUTION_NAME = os.environ.get("INSTITUTION_NAME", "IES Antonio García Bellido")
    APP_YEAR = int(os.environ.get("APP_YEAR", "2026"))

    BASE_DIR = Path(__file__).resolve().parent
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")

    DATABASE_URL = os.environ.get("DATABASE_URL")

    # URLs públicas de cada app (sin barra final). En local: APP_INCIDENCIAS_URL o USE_LOCAL_INCIDENCIAS=1 (8001).
    _inci = (os.environ.get("APP_INCIDENCIAS_URL") or "").strip().rstrip("/")
    if not _inci and os.environ.get("USE_LOCAL_INCIDENCIAS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        _inci = "http://127.0.0.1:8001"
    APP_INCIDENCIAS_URL = _inci
    APP_RESERVAS_URL = (os.environ.get("APP_RESERVAS_URL") or "").strip().rstrip("/")
    APP_MOSCOSOS_URL = (os.environ.get("APP_MOSCOSOS_URL") or "").strip().rstrip("/")

    # Documentación moscoso (Anexo I por correo)
    MOSCOSOS_DOCS_TO = (
        os.environ.get("MOSCOSOS_DOCS_TO") or "pabloceballos@yahoo.com"
    ).strip()
    MOSCOSOS_DOCS_FROM = (os.environ.get("MOSCOSOS_DOCS_FROM") or "").strip()
    SMTP_HOST = (os.environ.get("SMTP_HOST") or "").strip()
    SMTP_PORT = int(os.environ.get("SMTP_PORT") or "587")
    SMTP_USER = (os.environ.get("SMTP_USER") or "").strip()
    SMTP_PASSWORD = (os.environ.get("SMTP_PASSWORD") or "").strip()
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    # Solo desarrollo local: marca documentación enviada sin SMTP (no usar en producción).
    MOSCOSOS_DOCS_DEV_SIMULATE = os.environ.get(
        "MOSCOSOS_DOCS_DEV_SIMULATE", ""
    ).strip().lower() in ("1", "true", "yes")

settings = Settings()
