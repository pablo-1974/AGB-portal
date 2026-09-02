-- Primera aceptación de normas de uso (app reservas)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS reservas_normas_accepted_at TIMESTAMPTZ;
