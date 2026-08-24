-- Primera aceptación de normas de reserva (app moscosos)
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS moscosos_normas_accepted_at TIMESTAMPTZ;
