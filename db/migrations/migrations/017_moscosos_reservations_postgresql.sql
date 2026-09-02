-- Reservas de días de moscoso por curso escolar (máx. 2 plazas por día).

CREATE TABLE IF NOT EXISTS moscosos_reservations (
    id                  SERIAL PRIMARY KEY,
    school_calendar_id  INTEGER NOT NULL
        REFERENCES school_calendar(id) ON DELETE CASCADE,
    user_id             INTEGER NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
    reservation_date    DATE NOT NULL,
    trimester           SMALLINT NOT NULL
        CHECK (trimester >= 1 AND trimester <= 3),
    slot                SMALLINT NOT NULL
        CHECK (slot >= 1 AND slot <= 2),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (school_calendar_id, reservation_date, slot),
    UNIQUE (school_calendar_id, user_id, reservation_date)
);

CREATE INDEX IF NOT EXISTS ix_moscosos_reservations_cal_date
    ON moscosos_reservations (school_calendar_id, reservation_date);

CREATE INDEX IF NOT EXISTS ix_moscosos_reservations_user
    ON moscosos_reservations (school_calendar_id, user_id);
