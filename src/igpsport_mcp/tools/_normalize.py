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


def _iso_datetime(value: Any, tz: str = "+08:00") -> str | None:
    """Convert "YYYY-MM-DD HH:MM:SS" (Asia/Shanghai local) to ISO 8601 w/ offset."""
    if not value:
        return None
    text = str(value).strip().replace("/", "-")
    if " " in text:
        text = text.replace(" ", "T", 1)
    if "T" in text and "+" not in text and not text.endswith("Z"):
        text += tz
    return text


def normalize_list_row(row: dict[str, Any]) -> dict[str, Any]:
    ride_id = _first(row, "rideId", "id", "activityId")
    distance_m = _first(row, "rideDistance")
    speed_ms = _first(row, "avgSpeed")
    return {
        "ride_id": str(ride_id) if ride_id is not None else None,
        "name": _first(row, "title", "name"),
        "start_time": _iso_date(_first(row, "startTime")),
        "duration_s": _first(row, "totalMovingTime", "recordTime"),
        "distance_km": round(distance_m / 1000, 2) if distance_m is not None else None,
        "elevation_gain_m": _first(row, "totalAscent"),
        "avg_speed_kmh": round(speed_ms * 3.6, 1) if speed_ms is not None else None,
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
    # Power/HR are intentionally absent: the queryMyActivity payload has neither,
    # and surfacing them as null misleads the LLM into "no power meter / no HR
    # sensor". Per-ride power/HR live in get_activity_summary (parsed from FIT).
    return {
        "ride_id": item["ride_id"],
        "name": item["name"],
        "start_time": item["start_time"],
        "duration_s": item["duration_s"],
        "distance_km": item["distance_km"],
        "elevation_gain_m": item["elevation_gain_m"],
        "avg_speed_kmh": item["avg_speed_kmh"],
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
            round(detail["avgSlope"] * 100, 1) if detail.get("avgSlope") is not None else None
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
            "male" if row.get("gender") == 1 else "female" if row.get("gender") == 2 else None
        ),
    }


def normalize_segment_effort(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single segment effort (personal record) row."""
    return {
        "ride_id": str(row["rideId"]) if row.get("rideId") else None,
        "title": row.get("title"),
        "start_date": _iso_date(row.get("rideStartTime")),
        "time_s": row.get("rideTotalTime"),
        "avg_speed_kmh": (round(row["avgSpeed"], 1) if row.get("avgSpeed") is not None else None),
    }


# -- member statistics helpers ----------------------------------------------

# keyName -> (output unit, raw->display converter). Raw values come in SI base
# units (metres, seconds, m/s); power is already watts and ascent already metres.
_PB_UNITS: dict[str, tuple[str, Any]] = {
    "MaxDistance": ("km", lambda v: round(v / 1000, 2)),
    "MaxTime": ("h", lambda v: round(v / 3600, 2)),
    "MaxAvgSpeed": ("km/h", lambda v: round(v * 3.6, 2)),
    "MaxMaxSpeed": ("km/h", lambda v: round(v * 3.6, 2)),
    "MaxClimbinSpeed": ("m", lambda v: round(v, 1)),
    "MaxAvgPower": ("W", lambda v: round(v)),
    "MaxMaxPower": ("W", lambda v: round(v)),
}


def normalize_personal_best(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single personal-best (PR) row, converting to display units."""
    try:
        raw = float(row["keyValue"]) if row.get("keyValue") is not None else None
    except (TypeError, ValueError):
        raw = None
    unit: str | None = None
    value: float | None = raw
    conv = _PB_UNITS.get(row.get("keyName"))
    if conv and raw is not None:
        unit, fn = conv
        value = fn(raw)
    return {
        "metric": row.get("keyName"),
        "label": row.get("keyLabel"),
        "value": value,
        "unit": unit,
        "ride_id": str(row["activityId"]) if row.get("activityId") else None,
        "achieved_at": _iso_datetime(row.get("keyTime")),
    }


def normalize_stat_axis(point: dict[str, Any]) -> dict[str, Any]:
    """Normalize one bucket of the monthly distance axis."""
    timer_s = point.get("totalTimerTime")
    return {
        "period": point.get("time"),
        "distance_km": point.get("value"),
        "ride_count": point.get("totalCount"),
        "duration_h": round(timer_s / 3600, 2) if timer_s is not None else None,
    }


def normalize_milestone(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a distance milestone (# of rides past a distance threshold)."""
    distance = row.get("distance")
    try:
        distance_km = int(float(distance)) if distance is not None else None
    except (TypeError, ValueError):
        distance_km = distance
    return {"distance_km": distance_km, "ride_count": row.get("count")}


def normalize_member_statistics(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize the getMemberDataStatistics response to compact, unit-corrected shape."""
    stats = data.get("statisticsData") or {}
    distance_m = stats.get("totalDistance")
    timer_s = stats.get("totalTimerTime")
    avg_speed = stats.get("avgSpeed")
    return {
        "totals": {
            "ride_count": stats.get("totalCount"),
            "distance_km": round(distance_m / 1000, 2) if distance_m is not None else None,
            "duration_h": round(timer_s / 3600, 2) if timer_s is not None else None,
            "elevation_m": stats.get("sumTotalAscent"),
            "calories_kcal": stats.get("totalCalories"),
            "avg_speed_kmh": round(avg_speed * 3.6, 2) if avg_speed is not None else None,
            "tss": stats.get("totalPwrTSS"),
        },
        "monthly": [normalize_stat_axis(p) for p in (data.get("axis") or [])],
        "milestones": [normalize_milestone(m) for m in (data.get("milestoneList") or [])],
        "personal_bests": [
            normalize_personal_best(b) for b in (data.get("personalBestList") or [])
        ],
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
