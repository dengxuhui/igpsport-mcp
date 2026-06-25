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
    for activity in activities:
        upsert_activity(conn, activity)


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


# -- workout CRUD -----------------------------------------------------------

_WO_COLS = (
    "workout_id",
    "title",
    "description",
    "total_time_s",
    "ir_json",
    "api_json",
    "created_at",
)


def save_workout(
    conn: sqlite3.Connection, workout_id: int, ir: dict[str, Any], api: dict[str, Any]
) -> None:
    """Record a successfully created workout."""
    row = {
        "workout_id": workout_id,
        "title": ir.get("title", ""),
        "description": ir.get("description", ""),
        "total_time_s": api.get("totalTime", 0),
        "ir_json": json.dumps(ir, ensure_ascii=False),
        "api_json": json.dumps(api, ensure_ascii=False),
        "created_at": _now_iso(),
    }
    placeholders = ", ".join(f":{c}" for c in _WO_COLS)
    conn.execute(
        f"INSERT OR REPLACE INTO workouts ({', '.join(_WO_COLS)}) VALUES ({placeholders})",
        row,
    )
    conn.commit()


def list_workouts(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """List recently created workouts (newest first)."""
    cur = conn.execute(
        "SELECT workout_id, title, description, total_time_s, created_at FROM workouts "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    return [dict(row) for row in cur.fetchall()]


def get_workout(conn: sqlite3.Connection, workout_id: int) -> dict[str, Any] | None:
    """Return full stored workout row or None."""
    cur = conn.execute("SELECT * FROM workouts WHERE workout_id = ?", (workout_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def delete_workout(conn: sqlite3.Connection, workout_id: int) -> bool:
    """Remove a workout from local storage. Returns True if it existed."""
    cur = conn.execute("DELETE FROM workouts WHERE workout_id = ?", (workout_id,))
    conn.commit()
    return cur.rowcount > 0
