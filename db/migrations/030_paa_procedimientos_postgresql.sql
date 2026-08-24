-- Procedimientos PAA (sanción: suspensión del derecho de asistencia).
-- Aplicar en Neon / PostgreSQL si hace falta (runtime también hace ensure_*).

CREATE TABLE IF NOT EXISTS paa_procedimientos (
    id              SERIAL PRIMARY KEY,
    student_id      INTEGER REFERENCES students(id) ON DELETE SET NULL,
    alumno          TEXT NOT NULL,
    grupo           TEXT NOT NULL,
    fecha_inicio    DATE NOT NULL,
    fecha_final     DATE NOT NULL,
    dias_lectivos   INTEGER NOT NULL CHECK (dias_lectivos >= 0),
    created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    notice_id       INTEGER REFERENCES portal_published_notices(id) ON DELETE SET NULL,
    CONSTRAINT paa_fechas_ok CHECK (fecha_inicio <= fecha_final)
);

CREATE INDEX IF NOT EXISTS idx_paa_fecha_inicio
    ON paa_procedimientos (fecha_inicio DESC);

CREATE INDEX IF NOT EXISTS idx_paa_grupo_alumno
    ON paa_procedimientos (grupo, alumno);

COMMENT ON TABLE paa_procedimientos IS
    'Procedimientos de Acuerdo Abreviado: días de suspensión de asistencia.';
