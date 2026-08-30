"""Límite de intentos de login por IP y bloqueo temporal de cuentas."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from db.action_logs import log_portal_action
from db.connection import get_db

IP_MAX_FAILURES = 5
IP_BLOCK_MINUTES = 30
USER_MAX_FAILURES = 10

_schema_ready = False


def ensure_login_security_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS login_ip_throttle (
                    ip_address TEXT PRIMARY KEY,
                    failed_count INT NOT NULL DEFAULT 0,
                    blocked_until TIMESTAMPTZ
                )
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS login_failed_count INT NOT NULL DEFAULT 0
                """
            )
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS login_locked BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
    _schema_ready = True


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ip_block_remaining_minutes(ip_address: str) -> int | None:
    """Minutos restantes de bloqueo IP, o None si no está bloqueada."""
    ensure_login_security_schema()
    ip = (ip_address or "").strip() or "unknown"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT blocked_until
                FROM login_ip_throttle
                WHERE ip_address = %s
                """,
                (ip,),
            )
            row = cur.fetchone()
    if not row or not row.get("blocked_until"):
        return None
    blocked_until = row["blocked_until"]
    if blocked_until.tzinfo is None:
        blocked_until = blocked_until.replace(tzinfo=timezone.utc)
    delta = blocked_until - _now()
    if delta.total_seconds() <= 0:
        clear_ip_throttle(ip)
        return None
    return max(1, int(delta.total_seconds() // 60) + (1 if delta.total_seconds() % 60 else 0))


def clear_ip_throttle(ip_address: str) -> None:
    ensure_login_security_schema()
    ip = (ip_address or "").strip() or "unknown"
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM login_ip_throttle WHERE ip_address = %s", (ip,))


def record_ip_login_failure(ip_address: str) -> int | None:
    """Registra fallo desde una IP. Devuelve minutos de bloqueo si se activa."""
    ensure_login_security_schema()
    ip = (ip_address or "").strip() or "unknown"
    now = _now()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT failed_count, blocked_until
                FROM login_ip_throttle
                WHERE ip_address = %s
                """,
                (ip,),
            )
            row = cur.fetchone()
            if row and row.get("blocked_until"):
                blocked = row["blocked_until"]
                if blocked.tzinfo is None:
                    blocked = blocked.replace(tzinfo=timezone.utc)
                if blocked > now:
                    delta = blocked - now
                    return max(
                        1,
                        int(delta.total_seconds() // 60)
                        + (1 if delta.total_seconds() % 60 else 0),
                    )
                failed_count = 0
            else:
                failed_count = int(row["failed_count"] or 0) if row else 0
            failed_count += 1
            blocked_until = None
            block_mins = None
            if failed_count >= IP_MAX_FAILURES:
                blocked_until = now + timedelta(minutes=IP_BLOCK_MINUTES)
                block_mins = IP_BLOCK_MINUTES
            cur.execute(
                """
                INSERT INTO login_ip_throttle (ip_address, failed_count, blocked_until)
                VALUES (%s, %s, %s)
                ON CONFLICT (ip_address) DO UPDATE
                SET failed_count = EXCLUDED.failed_count,
                    blocked_until = EXCLUDED.blocked_until
                """,
                (ip, failed_count, blocked_until),
            )
    return block_mins


def is_user_login_locked(user: dict) -> bool:
    return bool(user.get("login_locked"))


def record_user_login_failure(user_id: int) -> bool:
    """Incrementa fallos del usuario. Devuelve True si la cuenta queda bloqueada."""
    ensure_login_security_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET login_failed_count = login_failed_count + 1,
                    login_locked = (login_failed_count + 1 >= %s)
                WHERE id = %s
                RETURNING login_locked
                """,
                (USER_MAX_FAILURES, int(user_id)),
            )
            row = cur.fetchone()
    return bool(row and row.get("login_locked"))


def clear_user_login_failures(user_id: int) -> None:
    ensure_login_security_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET login_failed_count = 0
                WHERE id = %s
                """,
                (int(user_id),),
            )


def unlock_user_login(user_id: int) -> None:
    ensure_login_security_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET login_failed_count = 0, login_locked = FALSE
                WHERE id = %s
                """,
                (int(user_id),),
            )


def log_failed_login_attempt(
    *,
    user_id: int | None,
    email: str,
    ip_address: str,
    reason: str,
) -> None:
    detail = f"ip={ip_address}; email={email.strip().lower()}; {reason}"
    log_portal_action(
        user_id=user_id,
        action="login_failed",
        entity="login",
        entity_id=user_id,
        detail=detail,
    )
