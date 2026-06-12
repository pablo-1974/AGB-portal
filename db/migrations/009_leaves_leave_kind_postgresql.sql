-- Tipo de ausencia institucional por fila de baja (baja médica/administrativa vs excedencia).
-- Las sustituciones guardan leave_kind = 'baja' por defecto (no afecta al parte mensual).

BEGIN;

ALTER TABLE leaves ADD COLUMN IF NOT EXISTS leave_kind TEXT NOT NULL DEFAULT 'baja';

COMMIT;
