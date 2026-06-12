-- Horas de ausencia del alumnado y profesores acompañantes en actividades extraescolares.

ALTER TABLE extraescolares
    ADD COLUMN IF NOT EXISTS hours_mask INTEGER NOT NULL DEFAULT 127;

COMMENT ON COLUMN extraescolares.hours_mask IS
    'Máscara de horas lectivas afectadas (bits 0–6: 1ª…6ª y recreo). 127 = día completo.';

CREATE TABLE IF NOT EXISTS extraescolar_acompanantes (
    id               SERIAL PRIMARY KEY,
    extraescolar_id  INTEGER NOT NULL REFERENCES extraescolares(id) ON DELETE CASCADE,
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE extraescolar_acompanantes IS
    'Profesores que acompañan en la actividad (además del responsable).';

CREATE UNIQUE INDEX IF NOT EXISTS uq_extraescolar_acompanantes_actividad_user
    ON extraescolar_acompanantes (extraescolar_id, user_id);

CREATE INDEX IF NOT EXISTS idx_extraescolar_acompanantes_actividad
    ON extraescolar_acompanantes (extraescolar_id);
