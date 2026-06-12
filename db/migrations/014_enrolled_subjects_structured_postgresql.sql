-- Tabla estructurada de asignaturas matriculadas

CREATE TABLE IF NOT EXISTS enrolled_subjects (
    id SERIAL PRIMARY KEY,
    import_id INTEGER NOT NULL
        REFERENCES enrolled_subjects_imports(id) ON DELETE CASCADE,
    row_number INTEGER NOT NULL,
    alumno TEXT NOT NULL,
    materia_abrev TEXT,
    materia TEXT,
    bilingue TEXT,
    estudio TEXT,
    curso TEXT,
    nombre_grupo TEXT,
    caracteristicas TEXT,
    departamento TEXT
);

CREATE INDEX IF NOT EXISTS ix_enrolled_subjects_import
    ON enrolled_subjects (import_id, row_number);

CREATE INDEX IF NOT EXISTS ix_enrolled_subjects_alumno
    ON enrolled_subjects (LOWER(TRIM(alumno)));

DROP TABLE IF EXISTS enrolled_subjects_rows;

ALTER TABLE enrolled_subjects_imports DROP COLUMN IF EXISTS headers;
