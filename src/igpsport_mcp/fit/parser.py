"""fitparse wrapper: records / laps / session.

Handles missing fields, GPS dropouts, timestamps and temperature. Produces the
1Hz continuous time base required before any derived-metric computation
(spec §8.3). A single corrupt message must not drop the whole file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from fitparse import FitFile
from fitparse.utils import FitParseError

from ..exceptions import IGPSportError

# Semicircles -> degrees (FIT position encoding).
_SEMICIRCLE_TO_DEG = 180.0 / (2**31)


class FitParseFailed(IGPSportError):
    """The FIT file could not be opened/parsed at all."""


@dataclass(slots=True)
class ParsedActivity:
    records: list[dict[str, Any]] = field(default_factory=list)
    laps: list[dict[str, Any]] = field(default_factory=list)
    session: dict[str, Any] = field(default_factory=dict)


def _message_to_dict(message: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for fielddata in message:
        out[fielddata.name] = fielddata.value
    # Normalize GPS to degrees if present and still in semicircles (ints).
    for key in ("position_lat", "position_long"):
        val = out.get(key)
        if isinstance(val, int):
            out[key] = val * _SEMICIRCLE_TO_DEG
    return out


def parse_fit(path: Path) -> ParsedActivity:
    try:
        fit = FitFile(str(path))
        fit.parse()
    except (FitParseError, OSError, ValueError) as exc:
        raise FitParseFailed(f"Failed to parse FIT {path}: {exc}") from exc

    records: list[dict[str, Any]] = []
    laps: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []

    for name, sink in (("record", records), ("lap", laps), ("session", sessions)):
        for message in fit.get_messages(name):
            try:
                sink.append(_message_to_dict(message))
            except (FitParseError, ValueError):
                continue  # skip a single bad message, keep the rest

    return ParsedActivity(records=records, laps=laps, session=sessions[0] if sessions else {})


def resample_to_1hz(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Resample records to a continuous 1Hz time base (spec §8.3).

    Numeric channels are linearly interpolated across gaps up to 10s; longer
    gaps stay NaN so derived metrics don't invent data across stops.
    """
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    if "timestamp" not in df.columns:
        raise FitParseFailed("FIT records have no 'timestamp' field")

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.dropna(subset=["timestamp"]).set_index("timestamp").sort_index()

    numeric = df.select_dtypes(include="number")
    resampled = numeric.resample("1s").mean().interpolate(method="linear", limit=10)
    return resampled.reset_index()
