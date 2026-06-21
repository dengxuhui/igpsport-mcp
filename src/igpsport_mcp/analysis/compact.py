"""Compact stream format + downsampling.

Streams are always emitted as ``{channel: {unit, values: [...]}}`` bare arrays,
never ``[{time, power}, ...]`` (project red line, spec §6.1). Downsampling
averages non-overlapping windows of the 1Hz signal.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from typing import Any

import numpy as np

# Resolution label -> window size in seconds ("lap" is handled by the laps tool).
RESOLUTIONS: dict[str, int] = {"1s": 1, "5s": 5, "10s": 10, "30s": 30, "1min": 60}

CHANNEL_UNITS: dict[str, str] = {
    "power": "watts",
    "hr": "bpm",
    "cadence": "rpm",
    "speed": "kmh",
    "altitude": "m",
    "temp": "c",
}


def resolution_to_seconds(resolution: str) -> int:
    try:
        return RESOLUTIONS[resolution]
    except KeyError as exc:
        raise ValueError(
            f"Unknown resolution {resolution!r}; expected one of {sorted(RESOLUTIONS)}"
        ) from exc


def _clean(value: float) -> float | int | None:
    """JSON-friendly scalar: NaN -> None, whole floats -> int, else round(2)."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def downsample(values: Sequence[float], window_s: int) -> list[float | int | None]:
    """Average non-overlapping ``window_s``-wide windows of a 1Hz signal."""
    if window_s < 1:
        raise ValueError("window_s must be >= 1")
    arr = np.asarray(values, dtype="float64")
    if window_s == 1:
        return [_clean(v) for v in arr]

    n_windows = math.ceil(arr.size / window_s)
    padded = np.full(n_windows * window_s, np.nan)
    padded[: arr.size] = arr
    blocks = padded.reshape(n_windows, window_s)

    with warnings.catch_warnings():
        # all-NaN windows -> NaN (becomes None); suppress the empty-slice warning.
        warnings.simplefilter("ignore", category=RuntimeWarning)
        means = np.nanmean(blocks, axis=1)
    return [_clean(v) for v in means]


def to_compact(
    channels: dict[str, Sequence[float]],
    window_s: int = 1,
    units: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build the compact ``{channel: {unit, values}}`` payload (bare arrays)."""
    unit_map = {**CHANNEL_UNITS, **(units or {})}
    out: dict[str, Any] = {}
    for name, values in channels.items():
        out[name] = {
            "unit": unit_map.get(name, "unknown"),
            "values": downsample(values, window_s),
        }
    return out
