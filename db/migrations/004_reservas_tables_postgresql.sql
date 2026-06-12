-- =====================================================================
-- Reservas de aulas (PostgreSQL)
-- - App integrada en el portal (FastAPI)
-- - Uso: cuadrantes, reservas puntuales, recurrentes y borrado por rango
-- =====================================================================

CREATE TABLE IF NOT EXISTS room_reservations (
    id SERIAL PRIMARY KEY,
    grupo TEXT NOT NULL,
    room TEXT NOT NULL,
    reservation_date DATE NOT NULL,
    slot TEXT NOT NULL,
    reserved_for_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reserved_for_name TEXT NOT NULL,
    created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes TEXT
);

-- Evitar doble reserva en la misma aula/franja/día
CREATE UNIQUE INDEX IF NOT EXISTS uq_room_reservations_room_day_slot
    ON room_reservations (room, reservation_date, slot);

CREATE INDEX IF NOT EXISTS idx_room_reservations_day
    ON room_reservations (reservation_date);

CREATE INDEX IF NOT EXISTS idx_room_reservations_for_user
    ON room_reservations (reserved_for_user_id, reservation_date);


CREATE TABLE IF NOT EXISTS room_reservations_recurring (
    id SERIAL PRIMARY KEY,
    grupo TEXT NOT NULL,
    room TEXT NOT NULL,
    weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    slot TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NULL,
    reserved_for_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    reserved_for_name TEXT NOT NULL,
    created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_room_reservations_recurring_range
    ON room_reservations_recurring (start_date, end_date);

CREATE INDEX IF NOT EXISTS idx_room_reservations_recurring_for_user
    ON room_reservations_recurring (reserved_for_user_id);

