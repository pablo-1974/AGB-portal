-- Marca de envío de documentación (Anexo I); bloquea anulación de la reserva.

ALTER TABLE moscosos_reservations
    ADD COLUMN IF NOT EXISTS documentation_sent_at TIMESTAMPTZ;
