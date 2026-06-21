"""Training load: CTL / ATL / TSB via exponentially weighted daily TSS.

CTL = daily_tss.ewm(alpha=1/42); ATL = daily_tss.ewm(alpha=1/7); TSB = CTL-ATL
(spec §6.3). Rest days count as 0 TSS, so the input is reindexed to a
continuous daily range before the EWMA — otherwise the decay is wrong.
"""

from __future__ import annotations

import pandas as pd

CTL_ALPHA = 1 / 42
ATL_ALPHA = 1 / 7


def compute_load(daily_tss: pd.Series) -> pd.DataFrame:
    """Return a daily DataFrame with columns: tss, ctl, atl, tsb.

    ``daily_tss`` is indexed by date (sparse allowed); gaps are filled with 0
    across the full min..max daily range.
    """
    if daily_tss.empty:
        return pd.DataFrame(columns=["tss", "ctl", "atl", "tsb"])

    series = daily_tss.copy()
    series.index = pd.to_datetime(series.index).normalize()
    series = series.groupby(series.index).sum().sort_index()

    full_range = pd.date_range(series.index.min(), series.index.max(), freq="D")
    series = series.reindex(full_range, fill_value=0.0).astype("float64")

    ctl = series.ewm(alpha=CTL_ALPHA, adjust=False).mean()
    atl = series.ewm(alpha=ATL_ALPHA, adjust=False).mean()
    return pd.DataFrame({"tss": series, "ctl": ctl, "atl": atl, "tsb": ctl - atl})


def interpret_form(ctl: float, atl: float, tsb: float) -> str:
    """One-line, LLM-friendly summary of current fitness/fatigue/form."""
    if tsb < -30:
        form = "very overloaded"
    elif tsb < -10:
        form = "overloaded"
    elif tsb <= 5:
        form = "neutral"
    elif tsb <= 25:
        form = "fresh"
    else:
        form = "detraining / very fresh"
    return f"Form: {tsb:+.0f} ({form}), Fitness (CTL): {ctl:.0f}, Fatigue (ATL): {atl:.0f}"
