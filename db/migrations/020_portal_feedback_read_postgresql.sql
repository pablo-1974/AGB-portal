-- Lectura de avisos del portal (solo admin marca como leído)
ALTER TABLE portal_feedback
    ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS read_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_portal_feedback_read_at ON portal_feedback (read_at);
