-- Añade campo obligatorio `grupo` en reservas (puntuales y recurrentes)
-- Para instalaciones existentes.

ALTER TABLE room_reservations
ADD COLUMN IF NOT EXISTS grupo TEXT;

UPDATE room_reservations
SET grupo = 'SIN_GRUPO'
WHERE grupo IS NULL;

ALTER TABLE room_reservations
ALTER COLUMN grupo SET NOT NULL;

ALTER TABLE room_reservations_recurring
ADD COLUMN IF NOT EXISTS grupo TEXT;

UPDATE room_reservations_recurring
SET grupo = 'SIN_GRUPO'
WHERE grupo IS NULL;

ALTER TABLE room_reservations_recurring
ALTER COLUMN grupo SET NOT NULL;
