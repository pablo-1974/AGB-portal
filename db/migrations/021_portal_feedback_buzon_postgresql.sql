-- Varios buzones (funcionamiento del portal, mantenimiento, …)
ALTER TABLE portal_feedback
    ADD COLUMN IF NOT EXISTS buzon TEXT NOT NULL DEFAULT 'funcionamiento_portal';

UPDATE portal_feedback SET buzon = 'funcionamiento_portal' WHERE buzon IS NULL OR buzon = '';

ALTER TABLE portal_feedback DROP CONSTRAINT IF EXISTS portal_feedback_tipo_check;

CREATE INDEX IF NOT EXISTS idx_portal_feedback_buzon ON portal_feedback (buzon);
CREATE INDEX IF NOT EXISTS idx_portal_feedback_buzon_sent_at ON portal_feedback (buzon, sent_at DESC);
