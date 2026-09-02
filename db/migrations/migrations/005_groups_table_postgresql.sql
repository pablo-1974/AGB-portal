-- Tabla de grupos (portal general)
-- Campo funcional único: nombre

CREATE TABLE IF NOT EXISTS groups (
    name TEXT PRIMARY KEY,
    curso TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_groups_name_lower
ON groups (LOWER(name));
