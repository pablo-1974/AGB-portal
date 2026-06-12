-- Aviso en portal al director cuando un profesor envía documentación de moscoso.

ALTER TABLE moscosos_reservations
    ADD COLUMN IF NOT EXISTS documentation_director_notice_dismissed_at TIMESTAMPTZ;
