-- Anulación de actividades extraescolares (organizador, antes de la fecha).
ALTER TABLE extraescolares
    ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;
