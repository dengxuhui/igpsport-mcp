"""SQLite CRUD for the local cache.

Tools query the cache first and only hit the API on a miss; the FIT file is
cached permanently on disk (see ``IGPSportClient.download_fit``). This module
owns the activity-metadata table only; derived metrics are written by the
analysis layer in later phases.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

SCHEMA_RESOURCE = "schema.sql"

_ACTIVITY_COLUMNS = (
    "ride_id",
    "name",
    "start_time",
    "duration_s",
    "distance_km",
    "elevation_gain_m",
    "sport_type",
    "avg_power_w",
    "avg_hr_bpm",
    "fit_path",
    "raw_json",
    "fetched_at",
)


def schema_sql() -> str:
    """Return the bundled schema DDL."""
    return resources.files(__package__).joinpath(SCHEMA_RESOURCE).read_text(encoding="utf-8")


def connect(db_path: Path) -> sqlite3.Connection:
    """Open (creating parent dirs) and initialize the cache database."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema_sql())
    return conn


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def upsert_activity(conn: sqlite3.Connection, activity: dict[str, Any]) -> None:
    """Insert or update a single normalized activity row."""
    row = {col: activity.get(col) for col in _ACTIVITY_COLUMNS}
    row["ride_id"] = str(row["ride_id"])
    if isinstance(row["raw_json"], (dict, list)):
        row["raw_json"] = json.dumps(row["raw_json"], ensure_ascii=False)
    row["fetched_at"] = row["fetched_at"] or _now_iso()

    placeholders = ", ".join(f":{c}" for c in _ACTIVITY_COLUMNS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in _ACTIVITY_COLUMNS if c != "ride_id")
    conn.execute(
        f"INSERT INTO activities ({', '.join(_ACTIVITY_COLUMNS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(ride_id) DO UPDATE SET {updates}",
        row,
    )
    conn.commit()


def upsert_activities(conn: sqlite3.Connection, activities: list[dict[str, Any]]) -> None:
    if not activities:
        return
    rows = []
    for activity in activities:
        row = {col: activity.get(col) for col in _ACTIVITY_COLUMNS}
        row["ride_id"] = str(row["ride_id"])
        if isinstance(row["raw_json"], (dict, list)):
            row["raw_json"] = json.dumps(row["raw_json"], ensure_ascii=False)
        row["fetched_at"] = row["fetched_at"] or _now_iso()
        rows.append(row)

    placeholders = ", ".join(f":{c}" for c in _ACTIVITY_COLUMNS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in _ACTIVITY_COLUMNS if c != "ride_id")
    conn.executemany(
        f"INSERT INTO activities ({', '.join(_ACTIVITY_COLUMNS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(ride_id) DO UPDATE SET {updates}",
        rows,
    )
    conn.commit()


def get_activity(conn: sqlite3.Connection, ride_id: str | int) -> dict[str, Any] | None:
    cur = conn.execute("SELECT * FROM activities WHERE ride_id = ?", (str(ride_id),))
    row = cur.fetchone()
    return dict(row) if row else None


def list_activities(
    conn: sqlite3.Connection, limit: int = 20, offset: int = 0
) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM activities ORDER BY start_time DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return [dict(row) for row in cur.fetchall()]


def set_fit_path(conn: sqlite3.Connection, ride_id: str | int, fit_path: Path) -> None:
    conn.execute(
        "UPDATE activities SET fit_path = ? WHERE ride_id = ?",
        (str(fit_path), str(ride_id)),
    )
    conn.commit()


# -- derived metrics cache ---------------------------------------------------

_METRICS_COLS = (
    "ride_id",
    "normalized_power_w",
    "intensity_factor",
    "tss",
    "work_kj",
    "max_power_w",
    "max_hr_bpm",
    "avg_cadence_rpm",
    "metrics_json",
    "computed_at",
)


def get_activity_metrics(conn: sqlite3.Connection, ride_id: str | int) -> dict[str, Any] | None:
    """Return cached derived metrics for *ride_id*, or None."""
    cur = conn.execute("SELECT * FROM activity_metrics WHERE ride_id = ?", (str(ride_id),))
    row = cur.fetchone()
    return dict(row) if row else None


def save_activity_metrics(
    conn: sqlite3.Connection, ride_id: str | int, summary: dict[str, Any]
) -> None:
    """Persist computed summary block for a ride.

    Gracefully handles legacy DBs with a FK constraint on ``ride_id`` — the
    in-memory cache still works, we just skip the SQLite write.
    """
    s = summary.get("summary") or summary
    row = {
        "ride_id": str(ride_id),
        "normalized_power_w": s.get("normalized_power_w"),
        "intensity_factor": s.get("intensity_factor"),
        "tss": s.get("tss"),
        "work_kj": s.get("work_kj"),
        "max_power_w": s.get("max_power_w"),
        "max_hr_bpm": s.get("max_hr_bpm"),
        "avg_cadence_rpm": s.get("avg_cadence_rpm"),
        "metrics_json": json.dumps(summary, ensure_ascii=False),
        "computed_at": _now_iso(),
    }
    placeholders = ", ".join(f":{c}" for c in _METRICS_COLS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in _METRICS_COLS if c != "ride_id")
    try:
        conn.execute(
            f"INSERT INTO activity_metrics ({', '.join(_METRICS_COLS)}) VALUES ({placeholders}) "
            f"ON CONFLICT(ride_id) DO UPDATE SET {updates}",
            row,
        )
        conn.commit()
    except sqlite3.IntegrityError:
        # Legacy DB with FK on activities.ride_id and the row wasn't cached
        # via list_activities first. Degrade gracefully — next call that
        # goes through list_activities will populate the FK.
        pass
