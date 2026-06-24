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


# -- segment helpers --------------------------------------------------------


def normalize_segment_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single segment list item to the canonical shape."""
    return {
        "segments_id": row.get("id"),
        "title": row.get("title"),
        "distance_m": row.get("distance"),
        "avg_grade_pct": (
            round(row["avgSlope"] * 100, 1) if row.get("avgSlope") is not None else None
        ),
        "segments_num": row.get("segmentsNum"),
        "segments_status": row.get("segmentsStatus"),
        "image_url": row.get("filePath"),
        "my_record_s": row.get("myRecord"),
        "best_male_record_s": row.get("bestMaleRecord"),
        "best_female_record_s": row.get("bestFemaleRecord"),
    }


def normalize_segment_detail(detail: dict[str, Any]) -> dict[str, Any]:
    """Normalize the segment detail response to the canonical shape."""
    return {
        "segments_id": detail.get("id"),
        "title": detail.get("title"),
        "distance_m": detail.get("distance"),
        "total_ascent_m": detail.get("totalAscent"),
        "avg_grade_pct": (
            round(detail["avgSlope"] * 100, 1)
            if detail.get("avgSlope") is not None
            else None
        ),
        "min_alt_m": detail.get("minAlt"),
        "max_alt_m": detail.get("maxAlt"),
        "alt_diff_m": detail.get("altitudeDiff"),
        "segments_num": detail.get("segmentsNum"),
        "segments_status": detail.get("segmentsStatus"),
        "finish_people_count": detail.get("segmentsFinishPeopleCount"),
        "finish_count": detail.get("segmentsFinishCount"),
        "collect_count": detail.get("collectCount"),
        "comprehensive_score": detail.get("comprehensiveScore"),
        "province": detail.get("province"),
        "city": detail.get("city"),
        "image_url": detail.get("filePath"),
    }


def normalize_rank_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single leaderboard row."""
    return {
        "rank": row.get("rank"),
        "member_id": row.get("memberId"),
        "nickname": row.get("nickName"),
        "avatar_url": row.get("avatar"),
        "time_s": row.get("rideTotalTime"),
        "speed_kmh": round(row["avgSpeed"], 1) if row.get("avgSpeed") is not None else None,
        "finish_date": _iso_date(row.get("finishDate")),
        "gender": (
            "male" if row.get("gender") == 1
            else "female" if row.get("gender") == 2
            else None
        ),
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
