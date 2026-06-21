"""Power metrics: NP / IF / TSS / work, plus Coggan 7-zone distribution.

Formulas follow authoritative definitions exactly (spec §6.2). Inputs must be
resampled to a continuous 1Hz time base; NaN samples (recording gaps) are
ignored rather than treated as zero.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

# Coggan power-zone upper bounds as a fraction of FTP (Z7 = everything above).
POWER_ZONE_BOUNDS = (0.55, 0.75, 0.90, 1.05, 1.20, 1.50)
POWER_ZONE_COUNT = 7

_NP_WINDOW_S = 30


def normalized_power(power_1hz: Sequence[float]) -> float | None:
    """NP = (mean over time of rolling_30s_avg(power)^4)^0.25. Requires 1Hz input.

    Returns None when there are fewer than 30 valid seconds (NP undefined).
    """
    series = pd.Series(power_1hz, dtype="float64")
    rolling = series.rolling(window=_NP_WINDOW_S, min_periods=_NP_WINDOW_S).mean().dropna()
    if rolling.empty:
        return None
    mean_quartic = float((rolling**4).mean())
    if not math.isfinite(mean_quartic) or mean_quartic < 0:
        return None
    return mean_quartic**0.25


def intensity_factor(np_w: float, ftp_w: float) -> float | None:
    if not ftp_w or ftp_w <= 0:
        return None
    return np_w / ftp_w


def training_stress_score(duration_s: float, np_w: float, if_: float, ftp_w: float) -> float | None:
    if not ftp_w or ftp_w <= 0:
        return None
    return (duration_s * np_w * if_) / (ftp_w * 3600) * 100


def work_kj(power_1hz: Sequence[float]) -> float | None:
    """Total mechanical work. At 1Hz each sample is 1 J·s⁻¹ over 1 s -> J = W."""
    arr = np.asarray(power_1hz, dtype="float64")
    if arr.size == 0 or np.all(np.isnan(arr)):
        return None
    return float(np.nansum(arr)) / 1000.0


def power_zone_seconds(power_1hz: Sequence[float], ftp_w: float) -> dict[str, int] | None:
    """Seconds spent in each Coggan zone (z1..z7). Requires 1Hz input + FTP."""
    if not ftp_w or ftp_w <= 0:
        return None
    arr = np.asarray(power_1hz, dtype="float64")
    arr = arr[~np.isnan(arr)]
    bounds = [b * ftp_w for b in POWER_ZONE_BOUNDS]
    # np.digitize: index 0..6 -> zone 1..7 (right=False: value < bound goes left).
    zone_idx = np.digitize(arr, bounds, right=False)
    counts = np.bincount(zone_idx, minlength=POWER_ZONE_COUNT)
    return {f"z{i + 1}": int(counts[i]) for i in range(POWER_ZONE_COUNT)}


def power_zone_bounds(ftp_w: float) -> dict[str, list[float | None]] | None:
    """Coggan zone boundaries in watts: ``{z1: [lo, hi], ...}`` (z7 hi = None)."""
    if not ftp_w or ftp_w <= 0:
        return None
    edges: list[float | None] = [0.0, *[b * ftp_w for b in POWER_ZONE_BOUNDS], None]
    return {
        f"z{i + 1}": [
            round(edges[i], 1),
            None if edges[i + 1] is None else round(edges[i + 1], 1),
        ]
        for i in range(POWER_ZONE_COUNT)
    }
