-- Campo opcional en users (proyectos futuros). Idempotente.

ALTER TABLE users ADD COLUMN IF NOT EXISTS departamento TEXT;

COMMENT ON COLUMN users.departamento IS
    'Departamento o ámbito del usuario; reservado para uso futuro en la aplicación.';
