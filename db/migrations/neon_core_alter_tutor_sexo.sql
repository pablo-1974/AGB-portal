-- =====================================================================
-- Neon: solo añade columnas nuevas si ya tienes users / students creadas.
-- Ejecutar después de migraciones previas o sobre BD existente de incidencias.
-- =====================================================================

ALTER TABLE users ADD COLUMN IF NOT EXISTS tutor TEXT NULL;

COMMENT ON COLUMN users.tutor IS
    'Grupo del que es tutor (p.ej. 1º A); NULL o cadena vacía si no es tutor.';

ALTER TABLE students ADD COLUMN IF NOT EXISTS sexo CHAR(1) NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_students_sexo'
    ) THEN
        ALTER TABLE students ADD CONSTRAINT ck_students_sexo CHECK (
            sexo IS NULL OR sexo IN ('M', 'V')
        );
    END IF;
END $$;

COMMENT ON COLUMN students.sexo IS
    'M o V (según convención del centro); NULL si aún no está informado.';
