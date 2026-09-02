-- Expedientes disciplinarios (sanciones).
-- Inicio puede registrarse sin cierre ni sanción cautelar.

CREATE TABLE IF NOT EXISTS expedientes_disciplinarios (
    id                      SERIAL PRIMARY KEY,
    student_id              INTEGER REFERENCES students(id) ON DELETE SET NULL,
    alumno                  TEXT NOT NULL,
    grupo                   TEXT NOT NULL,
    fecha_inicio_expediente DATE NOT NULL,
    fecha_final_expediente  DATE,
    cautelar_inicio         DATE,
    cautelar_final          DATE,
    sancion_inicio          DATE,
    sancion_final           DATE,
    dias_lectivos           INTEGER NOT NULL DEFAULT 0 CHECK (dias_lectivos >= 0),
    instructor_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    instructor_nombre       TEXT NOT NULL,
    created_by              INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    notice_id               INTEGER REFERENCES portal_published_notices(id) ON DELETE SET NULL,
    CONSTRAINT exp_fechas_expediente_ok CHECK (
        fecha_final_expediente IS NULL
        OR fecha_inicio_expediente <= fecha_final_expediente
    ),
    CONSTRAINT exp_fechas_cautelar_ok CHECK (
        (cautelar_inicio IS NULL AND cautelar_final IS NULL)
        OR (
            cautelar_inicio IS NOT NULL
            AND cautelar_final IS NOT NULL
            AND cautelar_inicio <= cautelar_final
        )
    ),
    CONSTRAINT exp_fechas_sancion_ok CHECK (
        (sancion_inicio IS NULL AND sancion_final IS NULL)
        OR (
            sancion_inicio IS NOT NULL
            AND sancion_final IS NOT NULL
            AND sancion_inicio <= sancion_final
        )
    )
);

ALTER TABLE expedientes_disciplinarios
    ALTER COLUMN fecha_final_expediente DROP NOT NULL;
ALTER TABLE expedientes_disciplinarios
    ALTER COLUMN cautelar_inicio DROP NOT NULL;
ALTER TABLE expedientes_disciplinarios
    ALTER COLUMN cautelar_final DROP NOT NULL;
ALTER TABLE expedientes_disciplinarios
    ALTER COLUMN sancion_inicio DROP NOT NULL;
ALTER TABLE expedientes_disciplinarios
    ALTER COLUMN sancion_final DROP NOT NULL;
ALTER TABLE expedientes_disciplinarios
    ADD COLUMN IF NOT EXISTS notice_id INTEGER
        REFERENCES portal_published_notices(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_exp_inicio
    ON expedientes_disciplinarios (fecha_inicio_expediente DESC);

CREATE INDEX IF NOT EXISTS idx_exp_grupo_alumno
    ON expedientes_disciplinarios (grupo, alumno);

ALTER TABLE expedientes_disciplinarios
    ADD COLUMN IF NOT EXISTS notice_cierre_id INTEGER
        REFERENCES portal_published_notices(id) ON DELETE SET NULL;
