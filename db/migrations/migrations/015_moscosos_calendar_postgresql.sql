-- Calendario de moscosos: exclusiones adicionales ligadas al calendario escolar activo.

CREATE TABLE IF NOT EXISTS moscosos_calendar_config (
    id                      SERIAL PRIMARY KEY,
    school_calendar_id      INTEGER NOT NULL UNIQUE
        REFERENCES school_calendar(id) ON DELETE CASCADE,
    buffer_school_days      INTEGER NOT NULL DEFAULT 7
        CHECK (buffer_school_days >= 0 AND buffer_school_days <= 30),
    extra_excluded_dates    JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_moscosos_calendar_config_cal
    ON moscosos_calendar_config (school_calendar_id);
