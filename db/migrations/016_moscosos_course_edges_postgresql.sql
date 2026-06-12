-- Inicio y fin de clases para zonas de exclusión en calendario de moscosos.

ALTER TABLE moscosos_calendar_config
    ADD COLUMN IF NOT EXISTS course_start_date DATE;

ALTER TABLE moscosos_calendar_config
    ADD COLUMN IF NOT EXISTS course_end_date DATE;
