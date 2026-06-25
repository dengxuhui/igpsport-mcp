-- SQLite schema for igpsport-mcp local cache (~/.cache/igpsport-mcp/activities.db).
-- Activity list/summary are cached so repeat requests for the same ride hit zero API.

CREATE TABLE IF NOT EXISTS activities (
    ride_id           TEXT PRIMARY KEY,
    name              TEXT,
    start_time        TEXT NOT NULL,           -- ISO 8601 with timezone
    duration_s        INTEGER,
    distance_km       REAL,
    elevation_gain_m  REAL,
    sport_type        TEXT,
    avg_power_w       REAL,
    avg_hr_bpm        REAL,
    fit_path          TEXT,                    -- local cached FIT, NULL until downloaded
    raw_json          TEXT,                    -- original list-item payload
    fetched_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_activities_start_time ON activities (start_time);

-- Derived metrics computed locally from the FIT; keyed by ride.
CREATE TABLE IF NOT EXISTS activity_metrics (
    ride_id              TEXT PRIMARY KEY REFERENCES activities (ride_id) ON DELETE CASCADE,
    normalized_power_w   REAL,
    intensity_factor     REAL,
    tss                  REAL,
    work_kj              REAL,
    max_power_w          REAL,
    max_hr_bpm           REAL,
    avg_cadence_rpm      REAL,
    metrics_json         TEXT,                 -- full computed summary blob
    computed_at          TEXT NOT NULL
);

-- Athlete profile / training parameters snapshot.
CREATE TABLE IF NOT EXISTS athlete_profile (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    profile_json TEXT NOT NULL,
    fetched_at   TEXT NOT NULL
);

-- Workouts created via MCP (keeps a local ID list so list_workouts works
-- without a server-side list endpoint).
CREATE TABLE IF NOT EXISTS workouts (
    workout_id    INTEGER PRIMARY KEY,
    title         TEXT NOT NULL,
    description   TEXT,
    total_time_s  INTEGER,
    ir_json       TEXT NOT NULL,    -- original LLM-facing IR
    api_json      TEXT NOT NULL,    -- compiled iGPSport request body
    created_at    TEXT NOT NULL
);
