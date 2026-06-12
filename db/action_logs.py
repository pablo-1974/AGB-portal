"""Registro de acciones (Ausencias, Incidencias, Reservas, Moscosos, Extraescolares, horarios)."""

from __future__ import annotations

import logging

from db.connection import get_db

_log = logging.getLogger(__name__)
_schema_ready = False


def ensure_action_logs_schema() -> None:
    """Crea o actualiza ``action_logs`` (idempotente; seguro llamar en cada escritura)."""
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS action_logs (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    action TEXT NOT NULL,
                    entity TEXT,
                    entity_id INTEGER,
                    detail TEXT,
                    module TEXT NOT NULL DEFAULT 'ausencias',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_action_logs_user_id ON action_logs (user_id)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_action_logs_action ON action_logs (action)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_action_logs_created_at ON action_logs (created_at)"
            )
            cur.execute(
                """
                ALTER TABLE action_logs
                ADD COLUMN IF NOT EXISTS module TEXT NOT NULL DEFAULT 'ausencias'
                """
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_action_logs_module ON action_logs (module)"
            )
    _schema_ready = True


def add_action_log(
    *,
    user_id: int | None,
    action: str,
    entity: str | None = None,
    entity_id: int | None = None,
    detail: str | None = None,
    module: str = "ausencias",
) -> None:
    ensure_action_logs_schema()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO action_logs (user_id, action, entity, entity_id, detail, module)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user_id, action, entity, entity_id, detail, module),
            )


def list_action_logs(*, limit: int = 200, module: str | None = "ausencias") -> list[dict]:
    ensure_action_logs_schema()
    safe_limit = max(1, min(int(limit), 1000))
    with get_db() as conn:
        with conn.cursor() as cur:
            if module == "ausencias":
                cur.execute(
                    """
                    SELECT l.id, l.user_id, u.name AS user_name, l.action, l.entity,
                           l.entity_id, l.detail, l.created_at
                    FROM action_logs l
                    LEFT JOIN users u ON u.id = l.user_id
                    WHERE l.module = 'ausencias' OR l.module IS NULL
                    ORDER BY l.created_at DESC, l.id DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
            elif module:
                cur.execute(
                    """
                    SELECT l.id, l.user_id, u.name AS user_name, l.action, l.entity,
                           l.entity_id, l.detail, l.created_at
                    FROM action_logs l
                    LEFT JOIN users u ON u.id = l.user_id
                    WHERE l.module = %s
                    ORDER BY l.created_at DESC, l.id DESC
                    LIMIT %s
                    """,
                    (module, safe_limit),
                )
            else:
                cur.execute(
                    """
                    SELECT l.id, l.user_id, u.name AS user_name, l.action, l.entity,
                           l.entity_id, l.detail, l.created_at
                    FROM action_logs l
                    LEFT JOIN users u ON u.id = l.user_id
                    ORDER BY l.created_at DESC, l.id DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )
            return list(cur.fetchall())


def _log_module_action(
    *,
    user_id: int | None,
    action: str,
    module: str,
    entity: str,
    entity_id: int | None = None,
    detail: str | None = None,
) -> None:
    try:
        add_action_log(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            detail=detail,
            module=module,
        )
    except Exception:
        _log.exception(
            "No se pudo registrar acción (module=%s, action=%s, entity_id=%s)",
            module,
            action,
            entity_id,
        )


def log_incident_action(
    *,
    user_id: int | None,
    action: str,
    entity_id: int | None = None,
    detail: str | None = None,
) -> None:
    _log_module_action(
        user_id=user_id,
        action=action,
        module="incidencias",
        entity="incident",
        entity_id=entity_id,
        detail=detail,
    )


def log_reservation_action(
    *,
    user_id: int | None,
    action: str,
    entity: str = "reservation",
    entity_id: int | None = None,
    detail: str | None = None,
) -> None:
    _log_module_action(
        user_id=user_id,
        action=action,
        module="reservas",
        entity=entity,
        entity_id=entity_id,
        detail=detail,
    )


def log_moscosos_action(
    *,
    user_id: int | None,
    action: str,
    entity: str = "moscoso_reservation",
    entity_id: int | None = None,
    detail: str | None = None,
) -> None:
    _log_module_action(
        user_id=user_id,
        action=action,
        module="moscosos",
        entity=entity,
        entity_id=entity_id,
        detail=detail,
    )


def log_extraescolares_action(
    *,
    user_id: int | None,
    action: str,
    entity: str = "extraescolar",
    entity_id: int | None = None,
    detail: str | None = None,
) -> None:
    _log_module_action(
        user_id=user_id,
        action=action,
        module="extraescolares",
        entity=entity,
        entity_id=entity_id,
        detail=detail,
    )
