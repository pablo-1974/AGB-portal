-- Datos maestros compartidos (ejecutar en Neon cuando unifiques esquemas).
-- La app de incidencias ya usa tablas users y students; aquí solo extensiones.

CREATE TABLE IF NOT EXISTS school_calendar (
    id              SERIAL PRIMARY KEY,
    school_year     TEXT NOT NULL,
    first_date      DATE NOT NULL,
    last_day        DATE NOT NULL,
    xmas_start      DATE,
    xmas_end        DATE,
    easter_start    DATE,
    easter_end      DATE,
    other_holidays  JSONB DEFAULT '{}'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    end_eso         DATE,
    end_fpb1        DATE,
    end_fpb2        DATE,
    end_fpm1        DATE,
    end_fpm2        DATE,
    end_bach1       DATE,
    end_bach2       DATE
);

ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_eso DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_fpb1 DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_fpb2 DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_fpm1 DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_fpm2 DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_bach1 DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_bach2 DATE;

ALTER TABLE users ADD COLUMN IF NOT EXISTS alias TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'activo';
ALTER TABLE users ADD COLUMN IF NOT EXISTS titular BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS tutor TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS departamento TEXT;

ALTER TABLE students ADD COLUMN IF NOT EXISTS grupo TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS sexo CHAR(1);
ALTER TABLE students ADD COLUMN IF NOT EXISTS email_student TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS email_mother TEXT;
ALTER TABLE students ADD COLUMN IF NOT EXISTS email_father TEXT;

CREATE TABLE IF NOT EXISTS groups (
    name TEXT PRIMARY KEY,
    curso TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_groups_name_lower
ON groups (LOWER(name));

-- ---------- ausencias ----------
CREATE TABLE IF NOT EXISTS schedule_slots (
    id SERIAL PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day_index INTEGER NOT NULL CHECK (day_index BETWEEN 0 AND 4),
    hour_index INTEGER NOT NULL CHECK (hour_index BETWEEN 0 AND 6),
    type TEXT NOT NULL CHECK (type IN ('CLASS', 'GUARD', 'OTHER')),
    guard_type TEXT,
    "group" TEXT,
    room TEXT,
    subject TEXT,
    source TEXT DEFAULT 'import'
);

CREATE INDEX IF NOT EXISTS idx_schedule_slots_teacher_id ON schedule_slots (teacher_id);
CREATE INDEX IF NOT EXISTS idx_schedule_slots_day_hour ON schedule_slots (day_index, hour_index);

CREATE TABLE IF NOT EXISTS leaves (
    id SERIAL PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    parent_leave_id INTEGER REFERENCES leaves(id) ON DELETE CASCADE,
    start_date DATE NOT NULL,
    end_date DATE,
    cause TEXT NOT NULL DEFAULT '',
    substitute_teacher_id INTEGER REFERENCES users(id),
    substitute_start_date DATE,
    substitute_end_date DATE,
    category TEXT,
    is_substitution BOOLEAN NOT NULL DEFAULT FALSE,
    leave_kind TEXT NOT NULL DEFAULT 'baja'
);

CREATE INDEX IF NOT EXISTS idx_leaves_teacher_id ON leaves (teacher_id);
CREATE INDEX IF NOT EXISTS idx_leaves_parent_leave_id ON leaves (parent_leave_id);

CREATE TABLE IF NOT EXISTS absences (
    id SERIAL PRIMARY KEY,
    teacher_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    hours_mask INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    category TEXT,
    CONSTRAINT uq_absences_teacher_date UNIQUE (teacher_id, date)
);

CREATE INDEX IF NOT EXISTS idx_absences_teacher_id ON absences (teacher_id);
CREATE INDEX IF NOT EXISTS idx_absences_date ON absences (date);

CREATE TABLE IF NOT EXISTS action_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity TEXT,
    entity_id INTEGER,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_action_logs_user_id ON action_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_action_logs_action ON action_logs (action);
CREATE INDEX IF NOT EXISTS idx_action_logs_created_at ON action_logs (created_at);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_students_sexo'
    ) THEN
        ALTER TABLE students ADD CONSTRAINT ck_students_sexo CHECK (
            sexo IS NULL OR sexo IN ('M', 'V')
        );
    END IF;
END $$;
