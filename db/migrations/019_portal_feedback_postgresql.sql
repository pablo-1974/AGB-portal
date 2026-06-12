-- Buzón: avisos de funcionamiento del portal (mal funcionamiento / sugerencias)
CREATE TABLE IF NOT EXISTS portal_feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    tipo TEXT NOT NULL CHECK (tipo IN ('mal_funcionamiento', 'sugerencia')),
    mensaje TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_portal_feedback_sent_at ON portal_feedback (sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_portal_feedback_user_id ON portal_feedback (user_id);
CREATE INDEX IF NOT EXISTS idx_portal_feedback_tipo ON portal_feedback (tipo);
