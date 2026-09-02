-- Añade campo `curso` en groups para instalaciones existentes.

ALTER TABLE groups
ADD COLUMN IF NOT EXISTS curso TEXT;
