-- Buzones independientes: una tabla por app

CREATE TABLE IF NOT EXISTS funcionamiento_portal_feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    tipo TEXT NOT NULL CHECK (tipo IN ('mal_funcionamiento', 'sugerencia')),
    mensaje TEXT NOT NULL,
    read_at TIMESTAMPTZ,
    read_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS mantenimiento_feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    tipo TEXT NOT NULL CHECK (tipo IN ('mantenimiento_edificio', 'mantenimiento_informatica')),
    mensaje TEXT NOT NULL,
    read_at TIMESTAMPTZ,
    read_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
);

-- Migrar datos legacy desde portal_feedback (si existe)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'portal_feedback') THEN
        INSERT INTO funcionamiento_portal_feedback (
            id, user_id, sent_at, tipo, mensaje, read_at, read_by_user_id
        )
        SELECT id, user_id, sent_at, tipo, mensaje, read_at, read_by_user_id
        FROM portal_feedback
        WHERE COALESCE(buzon, 'funcionamiento_portal') = 'funcionamiento_portal'
        ON CONFLICT (id) DO NOTHING;

        INSERT INTO mantenimiento_feedback (
            id, user_id, sent_at, tipo, mensaje, read_at, read_by_user_id
        )
        SELECT id, user_id, sent_at, tipo, mensaje, read_at, read_by_user_id
        FROM portal_feedback
        WHERE buzon = 'mantenimiento'
        ON CONFLICT (id) DO NOTHING;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_fpfb_sent_at ON funcionamiento_portal_feedback (sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_fpfb_user_id ON funcionamiento_portal_feedback (user_id);
CREATE INDEX IF NOT EXISTS idx_mantfb_sent_at ON mantenimiento_feedback (sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_mantfb_user_id ON mantenimiento_feedback (user_id);
