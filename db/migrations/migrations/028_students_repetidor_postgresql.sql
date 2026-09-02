-- Repetidor de curso (sí/no) en alumnado

ALTER TABLE students ADD COLUMN IF NOT EXISTS repetidor BOOLEAN;

COMMENT ON COLUMN students.repetidor IS 'Repite curso (sí/no).';
