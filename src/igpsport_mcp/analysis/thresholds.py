"""Estimate FTP and LTHR from historical activities.

When a rider has never done a formal test, FTP/LTHR can be approximated from
the power-duration / HR-duration "mean-max" curve aggregated across recent
activities. Methods follow authoritative definitions (Coggan 20-min test,
Monod-Scherrer critical-power model, Friel HR field test). Every estimate
carries a confidence level and a "do a formal test to confirm" caveat, and the
function never invents a number the data can't support (returns None instead).

Design notes:
- Peaks are aggregated across *all* activities in a time window, not taken from
  a single ride — one ride supplies the 5-min peak, another the 20-min peak.
- The default window is 42 days (the CTL time constant): older peaks may not
  reflect current form. It widens to 90 days only when the window is too sparse,
  and that widening downgrades confidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

# Mean-max sampling durations (seconds): sprint -> ~1h, covering the 20-min
# anchor plus the short/long points the CP model needs.
_DURATIONS_S = (5, 60, 180, 300, 480, 720, 1200, 1800, 3600)

_DEFAULT_WINDOW_DAYS = 42
_FALLBACK_WINDOW_DAYS = 90
_MIN_ACTIVITIES = 3

# CP linear work-time model anchors (best available short, best available long).
_CP_SHORT_S = (300, 180)
_CP_LONG_S = (1200, 720)

_LEVELS = ("low", "medium", "high")


@dataclass(frozen=True)
class ActivitySignal:
    """One activity's 1Hz channels for threshold estimation."""

    day: date
    power_1hz: Sequence[float] | None = None
    hr_1hz: Sequence[float] | None = None


def _nonempty(seq: Sequence[float] | None) -> bool:
    return seq is not None and len(seq) > 0


def _r(value: float | None) -> int | None:
    return None if value is None else round(value)


def _mean_max(series_1hz: Sequence[float], durations: tuple[int, ...]) -> dict[int, float]:
    """Best sustained average over each duration (max rolling mean). Requires 1Hz."""
    s = pd.Series(series_1hz, dtype="float64")
    n = len(s)
    out: dict[int, float] = {}
    for d in durations:
        if d > n:
            continue
        best = s.rolling(window=d, min_periods=d).mean().max()
        if pd.notna(best):
            out[d] = float(best)
    return out


def _aggregate(curves: list[dict[int, float]]) -> dict[int, float]:
    """Cross-activity max for each duration."""
    agg: dict[int, float] = {}
    for curve in curves:
        for d, v in curve.items():
            if v > agg.get(d, float("-inf")):
                agg[d] = v
    return agg


def _peak_hr(activities: list[ActivitySignal]) -> float | None:
    """Highest instantaneous HR sample seen across all activities."""
    peak = float("-inf")
    for a in activities:
        if _nonempty(a.hr_1hz):
            arr = np.asarray(a.hr_1hz, dtype="float64")
            if not np.all(np.isnan(arr)):
                peak = max(peak, float(np.nanmax(arr)))
    return None if peak == float("-inf") else peak


def _critical_power(mmp: dict[int, float]) -> float | None:
    """Monod-Scherrer linear model CP from a short and a long anchor.

    W(t) = W' + CP*t with W(t) = P*t, so
    CP = (P_long*t_long - P_short*t_short) / (t_long - t_short).
    """
    short = next(((t, mmp[t]) for t in _CP_SHORT_S if t in mmp), None)
    long_ = next(((t, mmp[t]) for t in _CP_LONG_S if t in mmp), None)
    if not short or not long_ or long_[0] <= short[0]:
        return None
    (t1, p1), (t2, p2) = short, long_
    cp = (p2 * t2 - p1 * t1) / (t2 - t1)
    if not np.isfinite(cp) or cp <= 0 or cp >= p1:
        return None
    return cp


def _downgrade(conf: str, n_activities: int, widened: bool) -> str:
    idx = _LEVELS.index(conf)
    if n_activities < _MIN_ACTIVITIES:
        idx -= 1
    if widened:
        idx -= 1
    return _LEVELS[max(0, idx)]


def _ftp_confidence(ftp_20: float, cp: float | None) -> str:
    """Agreement between the 20-min and CP estimates drives confidence.

    A CP far above the 20-min estimate means the short efforts dwarf the 20-min
    one — i.e. the 20-min effort was likely submaximal, so the estimate may
    underestimate FTP.
    """
    if cp is None:
        return "medium"
    diff = abs(cp - ftp_20) / ftp_20
    if diff < 0.05:
        return "high"
    if diff < 0.10:
        return "medium"
    return "low"


def _estimate_ftp(mmp: dict[int, float], n_activities: int, widened: bool) -> dict[str, Any] | None:
    best_60 = mmp.get(3600)
    best_20 = mmp.get(1200)
    best_5 = mmp.get(300)
    cp = _critical_power(mmp)

    evidence: dict[str, Any] = {
        "best_5min_w": _r(best_5),
        "best_20min_w": _r(best_20),
        "best_60min_w": _r(best_60),
        "cp_model_w": _r(cp),
        "n_activities": n_activities,
    }

    if best_60 is not None:
        value, method, conf = best_60, "60min_best", "high"
    elif best_20 is not None:
        value = best_20 * 0.95
        method = "20min_best*0.95"
        conf = _ftp_confidence(value, cp)
    elif cp is not None:
        value, method, conf = cp * 0.95, "cp_model*0.95", "low"
    else:
        return None

    conf = _downgrade(conf, n_activities, widened)
    out: dict[str, Any] = {
        "value": round(value),
        "method": method,
        "confidence": conf,
        "evidence": evidence,
    }
    if conf == "low":
        out["note"] = (
            "low-confidence estimate; no clear maximal effort detected, so this "
            "may underestimate — do a formal FTP test to confirm"
        )
    return out


def _estimate_lthr(
    mmhr: dict[int, float], max_hr: float | None, n_activities: int, widened: bool
) -> dict[str, Any] | None:
    best_20 = mmhr.get(1200)
    best_30 = mmhr.get(1800)

    evidence: dict[str, Any] = {
        "best_20min_hr": _r(best_20),
        "best_30min_hr": _r(best_30),
        "max_hr_seen": _r(max_hr),
        "n_activities": n_activities,
    }

    # HR estimates are inherently noisy (drift, heat, caffeine): never "high".
    if best_20 is not None:
        value, method, conf = best_20, "best_20min_hr", "medium"
    elif max_hr is not None:
        value, method, conf = max_hr * 0.90, "maxhr*0.90", "low"
    else:
        return None

    conf = _downgrade(conf, n_activities, widened)
    out: dict[str, Any] = {
        "value": round(value),
        "method": method,
        "confidence": conf,
        "evidence": evidence,
    }
    if conf == "low":
        out["note"] = (
            "rough estimate; HR drifts with heat/fatigue — do a 30-min TT field test to confirm"
        )
    return out


def _channel_count(activities: list[ActivitySignal]) -> int:
    n_power = sum(1 for a in activities if _nonempty(a.power_1hz))
    n_hr = sum(1 for a in activities if _nonempty(a.hr_1hz))
    return max(n_power, n_hr)


def estimate_thresholds(
    activities: Sequence[ActivitySignal],
    window_days: int = _DEFAULT_WINDOW_DAYS,
    reference_day: date | None = None,
) -> dict[str, Any]:
    """Estimate FTP and LTHR from recent activities' mean-max curves.

    Returns a compact dict with ``ftp`` / ``lthr`` blocks (each ``None`` when the
    data can't support an estimate), the window actually used, and per-channel
    activity counts. Estimates always carry a confidence level and a caveat.
    """
    if not activities:
        return {
            "ftp": None,
            "lthr": None,
            "window_days": window_days,
            "n_power_activities": 0,
            "n_hr_activities": 0,
            "note": "no activities provided",
        }

    ref = reference_day or max(a.day for a in activities)

    def in_window(days: int) -> list[ActivitySignal]:
        cutoff = ref - timedelta(days=days)
        return [a for a in activities if cutoff <= a.day <= ref]

    used = in_window(window_days)
    widened = False
    if _channel_count(used) < _MIN_ACTIVITIES:
        wide = in_window(_FALLBACK_WINDOW_DAYS)
        if _channel_count(wide) > _channel_count(used):
            used, window_days, widened = wide, _FALLBACK_WINDOW_DAYS, True

    p_curves = [_mean_max(a.power_1hz, _DURATIONS_S) for a in used if _nonempty(a.power_1hz)]
    h_curves = [_mean_max(a.hr_1hz, _DURATIONS_S) for a in used if _nonempty(a.hr_1hz)]
    mmp = _aggregate(p_curves)
    mmhr = _aggregate(h_curves)
    max_hr = _peak_hr(used)

    ftp = _estimate_ftp(mmp, len(p_curves), widened) if mmp else None
    lthr = (
        _estimate_lthr(mmhr, max_hr, len(h_curves), widened)
        if (mmhr or max_hr is not None)
        else None
    )

    return {
        "ftp": ftp,
        "lthr": lthr,
        "window_days": window_days,
        "reference_day": ref.isoformat(),
        "n_power_activities": len(p_curves),
        "n_hr_activities": len(h_curves),
        "note": "Estimates only — confirm with a formal test before relying on them for planning.",
    }
