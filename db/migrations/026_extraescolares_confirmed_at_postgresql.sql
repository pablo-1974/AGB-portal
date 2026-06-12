-- Confirmación del organizador: bloquea la edición de actividades futuras.

ALTER TABLE extraescolares
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;

COMMENT ON COLUMN extraescolares.confirmed_at IS
    'Momento en que el organizador confirma la actividad; a partir de entonces no es editable.';
