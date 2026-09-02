-- Mensaje de bienvenida del portal (primer acceso).
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS portal_welcome_accepted_at TIMESTAMPTZ;

-- Usuarios que ya habían entrado: no mostrar el mensaje de primer acceso.
UPDATE users
SET portal_welcome_accepted_at = COALESCE(last_login_at, created_at, now())
WHERE portal_welcome_accepted_at IS NULL
  AND last_login_at IS NOT NULL;

COMMENT ON COLUMN users.portal_welcome_accepted_at IS
    'Marca de lectura del mensaje de bienvenida del portal (primer acceso).';
