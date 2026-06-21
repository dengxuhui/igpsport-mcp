"""Map raw ``queryMyActivity`` rows to canonical, unit-corrected shapes.

The list endpoint returns distances in metres, speed in m/s and dotted dates
("2026.06.19") with no power/HR (those live in the FIT). Tools never see raw
rows — only the normalized item dicts produced here.
"""

from __future__ import annotations

from typing import Any

# Output stream channel -> FIT record column.
CHANNEL_FIELDS = {
    "power": "power",
    "hr": "heart_rate",
    "cadence": "cadence",
    "speed": "speed",
    "altitude": "altitude",
    "temp": "temperature",
}

# exerciseType -> sport label (0 = cycling per reverse-engineering notes §4.3).
_SPORT_BY_TYPE = {0: "cycling"}


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None


def _iso_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip().replace(".", "-").replace("/", "-")
    return text[:10] or None


def normalize_list_row(row: dict[str, Any]) -> dict[str, Any]:
    ride_id = _first(row, "rideId", "id", "activityId")
    distance_m = _first(row, "rideDistance")
    return {
        "ride_id": str(ride_id) if ride_id is not None else None,
        "name": _first(row, "title", "name"),
        "start_time": _iso_date(_first(row, "startTime")),
        "duration_s": _first(row, "totalMovingTime", "recordTime"),
        "distance_km": round(distance_m / 1000, 2) if distance_m is not None else None,
        "elevation_gain_m": _first(row, "totalAscent"),
        "exercise_type": _first(row, "exerciseType"),
        "raw": row,
    }


def matches(
    item: dict[str, Any],
    start_date: str | None,
    end_date: str | None,
    sport_type: str | None,
) -> bool:
    day = item.get("start_time")
    if start_date and day and day < start_date[:10]:
        return False
    if end_date and day and day > end_date[:10]:
        return False
    if sport_type:
        etype = item.get("exercise_type")
        if etype is not None and _SPORT_BY_TYPE.get(etype, str(etype)) != sport_type:
            return False
    return True


def to_list_output(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "ride_id": item["ride_id"],
        "name": item["name"],
        "start_time": item["start_time"],
        "duration_s": item["duration_s"],
        "distance_km": item["distance_km"],
        "elevation_gain_m": item["elevation_gain_m"],
        "avg_power_w": None,  # not in list payload; use get_activity_summary
        "avg_hr_bpm": None,
    }


def to_cache_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "ride_id": item["ride_id"],
        "name": item["name"],
        "start_time": item["start_time"],
        "duration_s": item["duration_s"],
        "distance_km": item["distance_km"],
        "elevation_gain_m": item["elevation_gain_m"],
        "sport_type": _SPORT_BY_TYPE.get(item.get("exercise_type")),
        "avg_power_w": None,
        "avg_hr_bpm": None,
        "raw_json": item["raw"],
    }
