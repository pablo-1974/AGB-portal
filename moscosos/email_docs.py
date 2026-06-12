"""Envío del Anexo I por correo (documentación de moscoso)."""

from __future__ import annotations

import smtplib
from datetime import date
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import settings
from db.school_calendar import MES_ES

MAX_PDF_BYTES = 5 * 1024 * 1024


class EmailDeliveryError(Exception):
    """Error al enviar el correo."""


class EmailNotConfiguredError(EmailDeliveryError):
    """Faltan variables SMTP en el entorno."""


def smtp_missing_keys() -> list[str]:
    """Nombres de variables de entorno que faltan para poder enviar correo."""
    missing: list[str] = []
    if not settings.SMTP_HOST:
        missing.append("SMTP_HOST")
    if not settings.SMTP_USER:
        missing.append("SMTP_USER")
    if not settings.SMTP_PASSWORD:
        missing.append("SMTP_PASSWORD")
    return missing


def is_smtp_configured() -> bool:
    return not smtp_missing_keys()


def _format_date_es(d: date) -> str:
    return f"{d.day} de {MES_ES[d.month].lower()} de {d.year}"


def build_anexo_subject(*, professor_name: str, reservation_date: date) -> str:
    name = (professor_name or "Profesor").strip()
    return f"Anexo I de {name} para el moscoso de {_format_date_es(reservation_date)}"


def send_anexo_email(
    *,
    professor_name: str,
    professor_email: str,
    reservation_date: date,
    pdf_bytes: bytes,
    pdf_filename: str,
) -> None:
    """Envía el PDF al buzón configurado en ``MOSCOSOS_DOCS_TO``."""
    missing = smtp_missing_keys()
    if missing:
        raise EmailNotConfiguredError(
            f"Faltan variables de entorno: {', '.join(missing)}."
        )

    host = settings.SMTP_HOST
    user = settings.SMTP_USER
    password = settings.SMTP_PASSWORD

    to_addr = settings.MOSCOSOS_DOCS_TO
    from_addr = settings.MOSCOSOS_DOCS_FROM or user
    subject = build_anexo_subject(
        professor_name=professor_name, reservation_date=reservation_date
    )

    body = (
        f"Documentación de moscoso enviada desde la aplicación del centro.\n\n"
        f"Profesor/a: {professor_name}\n"
        f"Correo del campus: {professor_email}\n"
        f"Fecha del moscoso reservado: {_format_date_es(reservation_date)}\n"
    )

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(body, "plain", "utf-8"))

    safe_name = pdf_filename if pdf_filename.lower().endswith(".pdf") else f"{pdf_filename}.pdf"
    part = MIMEApplication(pdf_bytes, _subtype="pdf")
    part.add_header("Content-Disposition", "attachment", filename=safe_name)
    msg.attach(part)

    try:
        with smtplib.SMTP(host, settings.SMTP_PORT, timeout=30) as smtp:
            if settings.SMTP_USE_TLS:
                smtp.starttls()
            smtp.login(user, password)
            smtp.sendmail(from_addr, [to_addr], msg.as_string())
    except EmailNotConfiguredError:
        raise
    except Exception as exc:
        raise EmailDeliveryError(f"No se pudo enviar el correo: {exc}") from exc
