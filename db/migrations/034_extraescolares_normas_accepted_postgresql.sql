-- Primera aceptación de normas (app actividades extraescolares)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS extraescolares_normas_accepted_at TIMESTAMPTZ;
