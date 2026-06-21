"""Heart-rate metrics: Friel/LTHR zones and hrTSS fallback.

hrTSS = (duration_s/3600) * (avg_hr/LTHR)^2 * 100, flagged "estimated from HR"
by the caller when used in place of power-based TSS (spec §6.3).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

# Friel HR-zone upper bounds as a fraction of LTHR (Z5 = everything at/above 100%).
HR_ZONE_BOUNDS = (0.81, 0.89, 0.94, 1.00)
HR_ZONE_COUNT = 5


def hr_tss(duration_s: float, avg_hr: float, lthr: float) -> float | None:
    if not lthr or lthr <= 0 or not avg_hr or avg_hr <= 0:
        return None
    return (duration_s / 3600) * (avg_hr / lthr) ** 2 * 100


def hr_zone_seconds(hr_1hz: Sequence[float], lthr: float) -> dict[str, int] | None:
    """Seconds spent in each Friel zone (z1..z5). Requires 1Hz input + LTHR."""
    if not lthr or lthr <= 0:
        return None
    arr = np.asarray(hr_1hz, dtype="float64")
    arr = arr[~np.isnan(arr)]
    bounds = [b * lthr for b in HR_ZONE_BOUNDS]
    zone_idx = np.digitize(arr, bounds, right=False)
    counts = np.bincount(zone_idx, minlength=HR_ZONE_COUNT)
    return {f"z{i + 1}": int(counts[i]) for i in range(HR_ZONE_COUNT)}


def hr_zone_bounds(lthr: float) -> dict[str, list[float | None]] | None:
    """Friel zone boundaries in bpm: ``{z1: [lo, hi], ...}`` (z5 hi = None)."""
    if not lthr or lthr <= 0:
        return None
    edges: list[float | None] = [0.0, *[b * lthr for b in HR_ZONE_BOUNDS], None]
    return {
        f"z{i + 1}": [
            round(edges[i], 1),
            None if edges[i + 1] is None else round(edges[i + 1], 1),
        ]
        for i in range(HR_ZONE_COUNT)
    }
