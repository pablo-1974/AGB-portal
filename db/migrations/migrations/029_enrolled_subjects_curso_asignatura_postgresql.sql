-- Curso de la asignatura (1.º, 2.º…) distinto del curso del alumno (columna curso).

ALTER TABLE enrolled_subjects
    ADD COLUMN IF NOT EXISTS curso_asignatura SMALLINT;

CREATE INDEX IF NOT EXISTS ix_enrolled_subjects_curso_asignatura
    ON enrolled_subjects (import_id, curso_asignatura)
    WHERE curso_asignatura IS NOT NULL;

CREATE TABLE IF NOT EXISTS enrolled_subject_catalog (
    materia_abrev TEXT NOT NULL PRIMARY KEY,
    materia TEXT,
    curso_asignatura SMALLINT NOT NULL,
    etapa TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
