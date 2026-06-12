"""Esquema de actividades extraescolares (Neon / PostgreSQL)."""

from __future__ import annotations

from db.connection import get_db

_schema_ready = False
_extras_ready = False
_extras_v2_ready = False
_extras_v3_ready = False


def _ensure_extraescolares_extras_v3(cur) -> None:
    global _extras_v3_ready
    if _extras_v3_ready:
        return
    cur.execute(
        """
        ALTER TABLE extraescolares
        ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ
        """
    )
    _extras_v3_ready = True


def _ensure_extraescolares_extras_v2(cur) -> None:
    global _extras_v2_ready
    if _extras_v2_ready:
        return
    cur.execute(
        """
        ALTER TABLE extraescolares
        ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ
        """
    )
    _extras_v2_ready = True


def _ensure_extraescolares_extras(cur) -> None:
    global _extras_ready
    if _extras_ready:
        return
    cur.execute(
        """
        ALTER TABLE extraescolares
        ADD COLUMN IF NOT EXISTS hours_mask INTEGER NOT NULL DEFAULT 127
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS extraescolar_acompanantes (
            id               SERIAL PRIMARY KEY,
            extraescolar_id  INTEGER NOT NULL
                REFERENCES extraescolares(id) ON DELETE CASCADE,
            user_id          INTEGER NOT NULL
                REFERENCES users(id) ON DELETE CASCADE,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_extraescolar_acompanantes_actividad_user
        ON extraescolar_acompanantes (extraescolar_id, user_id)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_extraescolar_acompanantes_actividad
        ON extraescolar_acompanantes (extraescolar_id)
        """
    )
    _extras_ready = True


def ensure_extraescolares_schema() -> None:
    global _schema_ready
    with get_db() as conn:
        with conn.cursor() as cur:
            if not _schema_ready:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS extraescolares (
                        id              SERIAL PRIMARY KEY,
                        fecha           DATE NOT NULL,
                        actividad       TEXT NOT NULL,
                        lugar           TEXT,
                        departamento    TEXT,
                        responsable_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_extraescolares_fecha
                    ON extraescolares (fecha)
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_extraescolares_responsable
                    ON extraescolares (responsable_id)
                    """
                )
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS extraescolar_alumnos (
                        id               SERIAL PRIMARY KEY,
                        extraescolar_id  INTEGER NOT NULL
                            REFERENCES extraescolares(id) ON DELETE CASCADE,
                        student_id       INTEGER REFERENCES students(id) ON DELETE SET NULL,
                        alumno           TEXT NOT NULL,
                        grupo            TEXT,
                        estado           TEXT NOT NULL DEFAULT 'no_confirmado'
                            CHECK (estado IN ('confirmado', 'no_confirmado')),
                        created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_extraescolar_alumnos_actividad
                    ON extraescolar_alumnos (extraescolar_id)
                    """
                )
                cur.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS uq_extraescolar_alumnos_actividad_student
                    ON extraescolar_alumnos (extraescolar_id, student_id)
                    WHERE student_id IS NOT NULL
                    """
                )
                _schema_ready = True
            _ensure_extraescolares_extras(cur)
            _ensure_extraescolares_extras_v2(cur)
            _ensure_extraescolares_extras_v3(cur)
