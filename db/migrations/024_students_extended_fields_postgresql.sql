-- Campos ampliados de alumnado (CIE, documento, contacto, transporte, etc.)

ALTER TABLE students ADD COLUMN IF NOT EXISTS cie TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS doc TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS fecha_nacimiento DATE;
ALTER TABLE students ADD COLUMN IF NOT EXISTS telefono1 TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS telefono2 TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS obs_tfno TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS difusion_imagen BOOLEAN;
ALTER TABLE students ADD COLUMN IF NOT EXISTS transporte BOOLEAN;
ALTER TABLE students ADD COLUMN IF NOT EXISTS parada TEXT;

COMMENT ON COLUMN students.cie IS 'Identificador CIE asignado por educación.';
COMMENT ON COLUMN students.doc IS 'Documento de identidad (NIF, NIE, etc.).';
COMMENT ON COLUMN students.fecha_nacimiento IS 'Fecha de nacimiento del alumno.';
COMMENT ON COLUMN students.telefono1 IS 'Teléfono de contacto principal.';
COMMENT ON COLUMN students.telefono2 IS 'Teléfono de contacto secundario.';
COMMENT ON COLUMN students.obs_tfno IS 'Observaciones sobre teléfonos (a quién llamar, etc.).';
COMMENT ON COLUMN students.difusion_imagen IS 'Autorización de difusión de imagen (sí/no).';
COMMENT ON COLUMN students.transporte IS 'Usa transporte escolar (sí/no).';
COMMENT ON COLUMN students.parada IS 'Parada de transporte escolar.';

CREATE INDEX IF NOT EXISTS idx_students_cie ON students (cie) WHERE cie IS NOT NULL;
