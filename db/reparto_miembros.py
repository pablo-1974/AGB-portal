"""Configuración de miembros de departamento (Reparto)."""

from __future__ import annotations

from db.connection import get_db

TABLE = "reparto_miembros"
HORAS_JORNADA_COMPLETA = 17

TIPO_FUNCIONARIO_DESTINO = "funcionario_destino"
TIPO_OTRO_FUNCIONARIO = "otro_funcionario"
TIPO_INTERINO = "interino"

TIPOS_MIEMBRO: tuple[tuple[str, str], ...] = (
    (TIPO_FUNCIONARIO_DESTINO, "Funcionario con destino"),
    (TIPO_OTRO_FUNCIONARIO, "Otro funcionario"),
    (TIPO_INTERINO, "Interino"),
)
TIPOS_MIEMBRO_IDS = frozenset(t[0] for t in TIPOS_MIEMBRO)
_schema_ready = False


def ensure_reparto_miembros_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE} (
                    departamento_abrev TEXT NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    horas INTEGER NOT NULL DEFAULT {HORAS_JORNADA_COMPLETA}
                        CHECK (horas >= 0),
                    jornada_completa BOOLEAN NOT NULL DEFAULT TRUE,
                    no_tutor BOOLEAN NOT NULL DEFAULT FALSE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (departamento_abrev, user_id)
                )
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS tipo TEXT
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS orden INTEGER
                """
            )
            cur.execute(
                f"""
                ALTER TABLE {TABLE}
                ADD COLUMN IF NOT EXISTS excluido BOOLEAN NOT NULL DEFAULT FALSE
                """
            )
    _schema_ready = True


def get_miembros_config(departamento_abrev: str) -> dict[int, dict]:
    """Config guardada por user_id."""
    ensure_reparto_miembros_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        return {}
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT user_id, horas, jornada_completa, no_tutor, tipo, orden, excluido
                FROM {TABLE}
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                """,
                (key,),
            )
            out: dict[int, dict] = {}
            for row in cur.fetchall():
                out[int(row["user_id"])] = {
                    "horas": int(row["horas"]),
                    "jornada_completa": bool(row["jornada_completa"]),
                    "no_tutor": bool(row["no_tutor"]),
                    "tipo": (str(row.get("tipo") or "").strip() or None),
                    "orden": int(row["orden"]) if row.get("orden") is not None else None,
                    "excluido": bool(row.get("excluido")),
                }
            return out


def save_miembros_config(
    *,
    departamento_abrev: str,
    rows: list[dict],
) -> None:
    """Sustituye la configuración de miembros de un departamento."""
    ensure_reparto_miembros_schema()
    key = (departamento_abrev or "").strip()
    if not key:
        raise ValueError("Departamento obligatorio")
    prev = get_miembros_config(key)
    form_ids = {int(r["user_id"]) for r in rows}
    excluidos = [
        uid for uid, cfg in prev.items() if cfg.get("excluido") and uid not in form_ids
    ]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {TABLE} WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))",
                (key,),
            )
            for r in rows:
                uid = int(r["user_id"])
                jornada = bool(r.get("jornada_completa"))
                horas = HORAS_JORNADA_COMPLETA if jornada else int(r.get("horas") or 0)
                if horas < 0:
                    horas = 0
                tipo_raw = str(r.get("tipo") or "").strip()
                tipo = tipo_raw if tipo_raw in TIPOS_MIEMBRO_IDS else None
                try:
                    orden = int(r.get("orden") or 0)
                except (TypeError, ValueError):
                    orden = 0
                if orden < 1:
                    orden = 0
                cur.execute(
                    f"""
                    INSERT INTO {TABLE} (
                        departamento_abrev, user_id, horas,
                        jornada_completa, no_tutor, tipo, orden, excluido, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, now())
                    """,
                    (
                        key,
                        uid,
                        horas,
                        jornada,
                        bool(r.get("no_tutor")),
                        tipo,
                        orden or None,
                    ),
                )
            for uid in excluidos:
                cfg = prev.get(uid) or {}
                cur.execute(
                    f"""
                    INSERT INTO {TABLE} (
                        departamento_abrev, user_id, horas,
                        jornada_completa, no_tutor, tipo, orden, excluido, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, now())
                    """,
                    (
                        key,
                        uid,
                        int(cfg.get("horas") or HORAS_JORNADA_COMPLETA),
                        bool(cfg.get("jornada_completa", True)),
                        bool(cfg.get("no_tutor")),
                        cfg.get("tipo"),
                        cfg.get("orden"),
                    ),
                )


def exclude_miembro(*, departamento_abrev: str, user_id: int) -> bool:
    """Oculta un miembro del listado del departamento."""
    ensure_reparto_miembros_schema()
    key = (departamento_abrev or "").strip()
    if not key or int(user_id) <= 0:
        return False
    uid = int(user_id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {TABLE}
                SET excluido = TRUE, updated_at = now()
                WHERE LOWER(BTRIM(departamento_abrev)) = LOWER(BTRIM(%s))
                  AND user_id = %s
                """,
                (key, uid),
            )
            if cur.rowcount > 0:
                return True
            cur.execute(
                f"""
                INSERT INTO {TABLE} (
                    departamento_abrev, user_id, horas,
                    jornada_completa, no_tutor, tipo, orden, excluido, updated_at
                )
                VALUES (%s, %s, %s, TRUE, FALSE, NULL, NULL, TRUE, now())
                """,
                (key, uid, HORAS_JORNADA_COMPLETA),
            )
    return True
