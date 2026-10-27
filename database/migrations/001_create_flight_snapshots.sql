CREATE TABLE IF NOT EXISTS flight_snapshots (
    id BIGSERIAL PRIMARY KEY,
    collected_at TIMESTAMPTZ NOT NULL,
    total_airborne INTEGER NOT NULL,
    average_speed_mps DOUBLE PRECISION NOT NULL,
    max_altitude_m DOUBLE PRECISION NOT NULL,
    top_flight_callsign TEXT NOT NULL,
    aircraft JSONB NOT NULL DEFAULT '[]'::jsonb,
    saved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE flight_snapshots
ADD COLUMN IF NOT EXISTS aircraft JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS flight_snapshots_collected_at_idx
ON flight_snapshots (collected_at DESC, id DESC);
