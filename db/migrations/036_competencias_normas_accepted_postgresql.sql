-- Primera aceptación de normas (app Evaluación de competencias)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS competencias_normas_accepted_at TIMESTAMPTZ;
