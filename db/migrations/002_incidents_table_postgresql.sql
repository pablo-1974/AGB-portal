-- =====================================================================
-- Neon (PostgreSQL): tabla `incidents`
-- Requiere que exista `public.users` (ids de profesores y revisores).
-- Ejecutar en SQL Editor de Neon o: psql $DATABASE_URL -f db/migrations/002_incidents_table_postgresql.sql
--
-- Nota: fecha, hora, created_at y closed_at son TEXT en el código actual
-- (formato ISO / franja tipo "1ª", "Recreo"; se puede normalizar a DATE/TIMESTAMP más adelante).
-- =====================================================================

CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,

    teacher_id INTEGER NOT NULL REFERENCES public.users (id) ON DELETE RESTRICT,
    teacher_name TEXT NOT NULL,

    grupo TEXT NOT NULL,
    alumno TEXT NOT NULL,

    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    hora_orden INTEGER NOT NULL,

    descripcion TEXT NOT NULL,
    gravedad_inicial TEXT NOT NULL,
    gravedad_final TEXT,

    estado TEXT NOT NULL,

    created_at TEXT NOT NULL,

    reviewed_by INTEGER REFERENCES public.users (id) ON DELETE SET NULL,
    reviewed_by_name TEXT,
    closed_at TEXT
);

COMMENT ON TABLE incidents IS 'Partes de incidencias de alumnado (app incidencias integrada en el campus).';
COMMENT ON COLUMN incidents.fecha IS 'Fecha en formato ISO (YYYY-MM-DD) como texto.';
COMMENT ON COLUMN incidents.hora IS 'Franja horaria (p.ej. 1ª, Recreo).';
COMMENT ON COLUMN incidents.estado IS 'Valores típicos: abierto, cerrado (ver utils.enums en la app).';

CREATE INDEX IF NOT EXISTS idx_incidents_fecha ON incidents (fecha);
CREATE INDEX IF NOT EXISTS idx_incidents_grupo_alumno ON incidents (grupo, alumno);
CREATE INDEX IF NOT EXISTS idx_incidents_teacher ON incidents (teacher_id);
CREATE INDEX IF NOT EXISTS idx_incidents_estado ON incidents (estado);
