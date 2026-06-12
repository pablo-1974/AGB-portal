-- Esquema mínimo para el portal (solo tabla users).
-- Ejecutar en PostgreSQL local (Docker o instalación propia), sobre una base vacía o nueva.
--
-- Cómo ejecutarlo (ejemplos):
--   psql "postgresql://agb:agb123@localhost:5432/agb_portal" -f db/migrations/000_minimal_users_local_postgresql.sql
-- O desde psql conectado: \i db/migrations/000_minimal_users_local_postgresql.sql
--
-- Después: arranca la app con DATABASE_URL apuntando a esa base y visita /
-- Si users está vacía → /register-first crea el primer admin.

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

CREATE INDEX IF NOT EXISTS idx_users_email_lower ON users (LOWER(email));
