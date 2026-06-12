-- =====================================================================
-- Neon (PostgreSQL): creación desde cero del núcleo compartido en public.
-- Ejecutar en el SQL Editor de Neon o con psql contra TU_DATABASE_URL.
--
-- Incluye: users (+ tutor), students (+ sexo M/V), school_calendar, groups.
-- La app de incidencias usa students(grupo, alumno) con UNIQUE(grupo, alumno).
-- =====================================================================

-- ---------- users ----------
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    alias TEXT,
    status TEXT NOT NULL DEFAULT 'activo',
    titular BOOLEAN NOT NULL DEFAULT TRUE,
    tutor TEXT NULL,
    departamento TEXT,
    password_hash TEXT,
    active SMALLINT NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by INTEGER REFERENCES users (id) ON DELETE SET NULL,
    last_login_at TIMESTAMPTZ
);

COMMENT ON COLUMN users.tutor IS
    'Grupo del que es tutor (p.ej. 1º A); NULL o cadena vacía si no es tutor.';

CREATE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));

-- ---------- students ----------
CREATE TABLE IF NOT EXISTS students (
    id SERIAL PRIMARY KEY,
    grupo TEXT NOT NULL,
    alumno TEXT NOT NULL,
    sexo CHAR(1) NULL,
    email_student TEXT,
    email_mother TEXT,
    email_father TEXT,
    cie TEXT,
    doc TEXT,
    fecha_nacimiento DATE,
    telefono1 TEXT,
    telefono2 TEXT,
    obs_tfno TEXT,
    difusion_imagen BOOLEAN,
    transporte BOOLEAN,
    parada TEXT,
    CONSTRAINT uq_students_grupo_alumno UNIQUE (grupo, alumno),
    CONSTRAINT ck_students_sexo CHECK (sexo IS NULL OR sexo IN ('M', 'V'))
);

COMMENT ON COLUMN students.alumno IS
    'Nombre del alumno (único campo de nombre; usado por la app de incidencias).';
COMMENT ON COLUMN students.sexo IS
    'M o V (según convención del centro); NULL si aún no está informado.';

CREATE INDEX IF NOT EXISTS idx_students_grupo ON students (grupo);

-- ---------- school_calendar ----------
CREATE TABLE IF NOT EXISTS school_calendar (
    id SERIAL PRIMARY KEY,
    school_year TEXT NOT NULL,
    first_date DATE NOT NULL,
    last_day DATE NOT NULL,
    xmas_start DATE,
    xmas_end DATE,
    easter_start DATE,
    easter_end DATE,
    other_holidays JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    end_eso DATE,
    end_fpb1 DATE,
    end_fpb2 DATE,
    end_fpm1 DATE,
    end_fpm2 DATE,
    end_bach1 DATE,
    end_bach2 DATE
);

ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_eso DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_fpb1 DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_fpb2 DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_fpm1 DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_fpm2 DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_bach1 DATE;
ALTER TABLE school_calendar ADD COLUMN IF NOT EXISTS end_bach2 DATE;

-- ---------- groups ----------
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
    type TEXT NOT NULL CHECK (type IN ('CLASS', 'GUARD')),
    guard_type TEXT,
    "group" TEXT,
    room TEXT,
    subject TEXT,
    source TEXT DEFAULT 'import'
);

CREATE INDEX IF NOT EXISTS idx_schedule_slots_teacher_id ON schedule_slots (teacher_id);
CREATE INDEX IF NOT EXISTS idx_schedule_slots_day_hour ON schedule_slots (day_index, hour_index);
CREATE INDEX IF NOT EXISTS idx_schedule_slots_type ON schedule_slots (type);

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
CREATE INDEX IF NOT EXISTS idx_leaves_start_date ON leaves (start_date);
CREATE INDEX IF NOT EXISTS idx_leaves_end_date ON leaves (end_date);

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
CREATE INDEX IF NOT EXISTS idx_action_logs_entity ON action_logs (entity);
CREATE INDEX IF NOT EXISTS idx_action_logs_entity_id ON action_logs (entity_id);
CREATE INDEX IF NOT EXISTS idx_action_logs_created_at ON action_logs (created_at);
