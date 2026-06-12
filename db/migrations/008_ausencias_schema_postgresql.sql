-- Integración DB de app "ausencias" en esquema compartido (Neon/PostgreSQL)
-- Seguro para ejecutar múltiples veces (idempotente).

BEGIN;

-- -------------------------------------------------------------------
-- 1) users fusionada (compatibilidad con AGB-apps-gestion + ausencias)
-- -------------------------------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS alias TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS titular BOOLEAN;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS active SMALLINT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN;
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_by INTEGER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

-- Defaults/no-null para instalación fusionada.
UPDATE users SET status = 'activo' WHERE status IS NULL;
UPDATE users SET titular = TRUE WHERE titular IS NULL;
UPDATE users SET active = 1 WHERE active IS NULL;
UPDATE users SET created_at = now() WHERE created_at IS NULL;
UPDATE users SET must_change_password = FALSE WHERE must_change_password IS NULL;

ALTER TABLE users ALTER COLUMN status SET DEFAULT 'activo';
ALTER TABLE users ALTER COLUMN titular SET DEFAULT TRUE;
ALTER TABLE users ALTER COLUMN active SET DEFAULT 1;
ALTER TABLE users ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE users ALTER COLUMN must_change_password SET DEFAULT FALSE;

ALTER TABLE users ALTER COLUMN status SET NOT NULL;
ALTER TABLE users ALTER COLUMN titular SET NOT NULL;
ALTER TABLE users ALTER COLUMN active SET NOT NULL;
ALTER TABLE users ALTER COLUMN created_at SET NOT NULL;
ALTER TABLE users ALTER COLUMN must_change_password SET NOT NULL;

-- En ausencias password_hash puede ser NULL (primer login / reset).
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;

-- created_by autorreferenciado (si no existe aún)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_created_by_fkey'
    ) THEN
        ALTER TABLE users
        ADD CONSTRAINT users_created_by_fkey
        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_active_check'
    ) THEN
        ALTER TABLE users
        ADD CONSTRAINT users_active_check CHECK (active IN (0, 1));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));
CREATE INDEX IF NOT EXISTS idx_users_alias ON users (alias);
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role);

-- -------------------------------------------------------------------
-- 2) schedule_slots
-- -------------------------------------------------------------------
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

-- -------------------------------------------------------------------
-- 3) leaves (incluye jerarquía de sustituciones)
-- -------------------------------------------------------------------
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

-- -------------------------------------------------------------------
-- 4) absences
-- -------------------------------------------------------------------
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

-- -------------------------------------------------------------------
-- 5) action_logs
-- -------------------------------------------------------------------
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

COMMIT;
