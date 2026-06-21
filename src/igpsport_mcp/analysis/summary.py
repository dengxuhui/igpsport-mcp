"""Assemble a single activity's derived-metric summary (spec §5.2).

Device-computed session values (avg/max/totals) are preferred where present —
they match what iGPSport displays — while NP / IF / TSS / work / zone time are
computed locally from the 1Hz record stream. Missing channels degrade to null.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ..fit.parser import ParsedActivity, resample_to_1hz
from . import hr as hr_mod
from . import power as power_mod

_MS_TO_KMH = 3.6


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _round(value: Any, ndigits: int = 1) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return round(float(value), ndigits)


def _col(df: pd.DataFrame, name: str) -> pd.Series | None:
    if name in df.columns and df[name].notna().any():
        return df[name]
    return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=UTC)
        return dt.isoformat()
    return str(value)


def build_summary(
    parsed: ParsedActivity, ftp_w: float | None = None, lthr_bpm: float | None = None
) -> dict[str, Any]:
    session = parsed.session or {}
    df = resample_to_1hz(parsed.records)

    duration_s = _first(session, "total_timer_time", "total_elapsed_time")
    if duration_s is None and not df.empty:
        span = df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]
        duration_s = span.total_seconds()
    duration_s = int(duration_s) if duration_s is not None else 0

    start_time = _iso(_first(session, "start_time")) or (
        _iso(df["timestamp"].iloc[0]) if not df.empty else None
    )

    power_s = _col(df, "power")
    hr_s = _col(df, "heart_rate")
    speed_session = _first(session, "enhanced_avg_speed", "avg_speed")
    speed_max = _first(session, "enhanced_max_speed", "max_speed")

    avg_power = _first(session, "avg_power")
    if avg_power is None and power_s is not None:
        avg_power = power_s.mean()
    avg_hr = _first(session, "avg_heart_rate")
    if avg_hr is None and hr_s is not None:
        avg_hr = hr_s.mean()

    np_w = power_mod.normalized_power(power_s.tolist()) if power_s is not None else None
    if_ = power_mod.intensity_factor(np_w, ftp_w) if (np_w and ftp_w) else None
    tss: float | None = None
    tss_estimated_from_hr = False
    if np_w is not None and if_ is not None and ftp_w:
        tss = power_mod.training_stress_score(duration_s, np_w, if_, ftp_w)
    elif avg_hr is not None and lthr_bpm:
        tss = hr_mod.hr_tss(duration_s, avg_hr, lthr_bpm)
        tss_estimated_from_hr = tss is not None

    summary = {
        "distance_km": _round((_first(session, "total_distance") or 0) / 1000, 2),
        "elevation_gain_m": _round(_first(session, "total_ascent")),
        "elevation_loss_m": _round(_first(session, "total_descent")),
        "avg_power_w": _round(avg_power),
        "max_power_w": _round(_first(session, "max_power")),
        "normalized_power_w": _round(np_w),
        "intensity_factor": _round(if_, 3),
        "tss": _round(tss),
        "work_kj": _round(power_mod.work_kj(power_s.tolist())) if power_s is not None else None,
        "avg_hr_bpm": _round(avg_hr),
        "max_hr_bpm": _round(_first(session, "max_heart_rate")),
        "avg_cadence_rpm": _round(_first(session, "avg_cadence")),
        "avg_speed_kmh": _round((speed_session or 0) * _MS_TO_KMH, 2),
        "max_speed_kmh": _round((speed_max or 0) * _MS_TO_KMH, 2),
        "avg_temp_c": _round(_first(session, "avg_temperature")),
    }

    return {
        "duration_s": duration_s,
        "start_time": start_time,
        "summary": summary,
        "hr_zones_s": hr_mod.hr_zone_seconds(hr_s.tolist(), lthr_bpm)
        if (hr_s is not None and lthr_bpm)
        else None,
        "power_zones_s": power_mod.power_zone_seconds(power_s.tolist(), ftp_w)
        if (power_s is not None and ftp_w)
        else None,
        "tss_estimated_from_hr": tss_estimated_from_hr,
    }
