-- Asignaturas matriculadas: registro de importaciones (histórico)
-- La tabla de datos es enrolled_subjects (ver 014_enrolled_subjects_structured_postgresql.sql)

CREATE TABLE IF NOT EXISTS enrolled_subjects_imports (
    id SERIAL PRIMARY KEY,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    imported_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    filename TEXT,
    row_count INTEGER NOT NULL DEFAULT 0
);
