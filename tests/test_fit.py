from datetime import UTC, datetime, timedelta

import pandas as pd

from igpsport_mcp.analysis import power
from igpsport_mcp.fit.parser import ParsedActivity, parse_fit, resample_to_1hz


def test_resample_to_1hz_fills_small_gaps():
    base = datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC)
    records = [
        {"timestamp": base, "power": 100, "heart_rate": 120},
        {"timestamp": base + timedelta(seconds=3), "power": 160, "heart_rate": 150},
    ]
    df = resample_to_1hz(records)
    # 0..3s inclusive -> 4 rows at 1s spacing.
    assert len(df) == 4
    deltas = df["timestamp"].diff().dropna().dt.total_seconds().unique()
    assert list(deltas) == [1.0]
    # linear interpolation across the 3s gap.
    assert df["power"].tolist() == [100.0, 120.0, 140.0, 160.0]


def test_resample_empty_records():
    assert resample_to_1hz([]).empty


def test_resample_long_gap_left_nan():
    base = datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC)
    records = [
        {"timestamp": base, "power": 100},
        {"timestamp": base + timedelta(seconds=30), "power": 200},
    ]
    df = resample_to_1hz(records)
    # gap of 30s exceeds the interpolation limit (10s) -> middle stays NaN.
    assert df["power"].isna().any()


def test_parse_real_fit(sample_fit):
    activity = parse_fit(sample_fit)
    assert isinstance(activity, ParsedActivity)
    assert len(activity.records) > 0
    assert "timestamp" in activity.records[0]
    # GPS, when present, is normalized to degrees (not raw semicircles).
    for rec in activity.records:
        lat = rec.get("position_lat")
        if lat is not None:
            assert -90.0 <= lat <= 90.0
            break
    df = resample_to_1hz(activity.records)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


def test_real_activity_power_metrics_are_sane(sample_fit):
    """End-to-end parse -> 1Hz -> NP/work on a real ride; sanity-range check.

    The exact <2% vs iGPSport comparison needs the user's displayed values;
    this guards that the pipeline produces physically plausible numbers.
    """
    df = resample_to_1hz(parse_fit(sample_fit).records)
    if "power" not in df.columns:
        import pytest

        pytest.skip("sample ride has no power channel")

    watts = df["power"].tolist()
    np_value = power.normalized_power(watts)
    work = power.work_kj(watts)
    max_power = df["power"].max()

    assert np_value is not None and 0 < np_value <= max_power
    assert work is not None and work > 0
