-- Actividades extraescolares: actividad principal y alumnado inscrito con estado de confirmación.

CREATE TABLE IF NOT EXISTS extraescolares (
    id              SERIAL PRIMARY KEY,
    fecha           DATE NOT NULL,
    actividad       TEXT NOT NULL,
    lugar           TEXT,
    departamento    TEXT,
    responsable_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE extraescolares IS
    'Actividades extraescolares del centro (fecha, actividad, lugar, departamento organizador y profesor responsable).';

COMMENT ON COLUMN extraescolares.fecha IS 'Fecha de la actividad.';
COMMENT ON COLUMN extraescolares.actividad IS 'Nombre o descripción breve de la actividad.';
COMMENT ON COLUMN extraescolares.lugar IS 'Lugar donde se realiza.';
COMMENT ON COLUMN extraescolares.departamento IS 'Departamento didáctico que organiza la actividad.';
COMMENT ON COLUMN extraescolares.responsable_id IS 'Usuario (profesor) que crea o gestiona la actividad.';

CREATE INDEX IF NOT EXISTS idx_extraescolares_fecha ON extraescolares (fecha);
CREATE INDEX IF NOT EXISTS idx_extraescolares_responsable ON extraescolares (responsable_id);
CREATE INDEX IF NOT EXISTS idx_extraescolares_departamento ON extraescolares (departamento);

CREATE TABLE IF NOT EXISTS extraescolar_alumnos (
    id               SERIAL PRIMARY KEY,
    extraescolar_id  INTEGER NOT NULL REFERENCES extraescolares(id) ON DELETE CASCADE,
    student_id       INTEGER REFERENCES students(id) ON DELETE SET NULL,
    alumno           TEXT NOT NULL,
    grupo            TEXT,
    estado           TEXT NOT NULL DEFAULT 'no_confirmado'
        CHECK (estado IN ('confirmado', 'no_confirmado')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE extraescolar_alumnos IS
    'Alumnado asociado a cada actividad extraescolar, con estado de confirmación.';

COMMENT ON COLUMN extraescolar_alumnos.student_id IS
    'Referencia opcional al alumno en students; alumno/grupo se guardan por si cambia el maestro de datos.';
COMMENT ON COLUMN extraescolar_alumnos.estado IS
    'confirmado | no_confirmado';

CREATE INDEX IF NOT EXISTS idx_extraescolar_alumnos_actividad
    ON extraescolar_alumnos (extraescolar_id);
CREATE INDEX IF NOT EXISTS idx_extraescolar_alumnos_estado
    ON extraescolar_alumnos (extraescolar_id, estado);

CREATE UNIQUE INDEX IF NOT EXISTS uq_extraescolar_alumnos_actividad_student
    ON extraescolar_alumnos (extraescolar_id, student_id)
    WHERE student_id IS NOT NULL;
