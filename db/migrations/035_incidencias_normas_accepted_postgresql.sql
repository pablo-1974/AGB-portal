-- Primera aceptación de normas (app incidencias)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS incidencias_normas_accepted_at TIMESTAMPTZ;
