from datetime import date, timedelta

import pytest

from igpsport_mcp.analysis import thresholds as th
from igpsport_mcp.analysis.thresholds import ActivitySignal


def _act(day_offset=0, power=None, hr=None, ref=date(2026, 6, 30)):
    return ActivitySignal(day=ref - timedelta(days=day_offset), power_1hz=power, hr_1hz=hr)


# -- mean-max --------------------------------------------------------------


def test_mean_max_constant_power():
    mm = th._mean_max([300.0] * 1300, th._DURATIONS_S)
    assert mm[300] == pytest.approx(300.0)
    assert mm[1200] == pytest.approx(300.0)
    # 30-min window longer than the series -> absent.
    assert 1800 not in mm


def test_mean_max_skips_durations_longer_than_series():
    mm = th._mean_max([200.0] * 100, th._DURATIONS_S)
    assert set(mm) == {5, 60}


def test_aggregate_takes_cross_activity_peak():
    a = {5: 600.0, 300: 400.0}
    b = {300: 350.0, 1200: 280.0}
    assert th._aggregate([a, b]) == {5: 600.0, 300: 400.0, 1200: 280.0}


# -- critical power --------------------------------------------------------


def test_critical_power_hand_computed():
    # short (300s, 300W), long (1200s, 250W):
    # CP = (250*1200 - 300*300)/(1200-300) = 210000/900 = 233.33
    cp = th._critical_power({300: 300.0, 1200: 250.0})
    assert cp == pytest.approx(233.333, rel=1e-3)


def test_critical_power_none_without_anchors():
    assert th._critical_power({300: 300.0}) is None  # no long anchor
    assert th._critical_power({1200: 250.0}) is None  # no short anchor


def test_critical_power_rejects_nonphysical():
    # Long power >= short power -> CP would exceed short power: rejected.
    assert th._critical_power({300: 200.0, 1200: 260.0}) is None


# -- FTP estimation --------------------------------------------------------


def test_ftp_from_20min_with_agreeing_cp_is_high():
    # 5-min activity @300W and two 20-min activities @250W: best_5=300, best_20=250.
    # ftp_20 = 237.5; CP = 233.33; diff < 5% -> high (n>=3, not widened).
    acts = [
        _act(1, power=[300.0] * 300),
        _act(2, power=[250.0] * 1200),
        _act(3, power=[250.0] * 1200),
    ]
    out = th.estimate_thresholds(acts)
    ftp = out["ftp"]
    assert ftp["method"] == "20min_best*0.95"
    assert ftp["value"] == 238
    assert ftp["confidence"] == "high"
    assert ftp["evidence"]["best_20min_w"] == 250
    assert ftp["evidence"]["best_5min_w"] == 300


def test_ftp_low_confidence_when_short_efforts_dominate():
    # Strong 5-min (450W) but weak 20-min (200W) -> CP >> ftp_20 -> submaximal 20min.
    acts = [
        _act(1, power=[450.0] * 300),
        _act(2, power=[200.0] * 1200),
        _act(3, power=[200.0] * 1200),
    ]
    out = th.estimate_thresholds(acts)
    ftp = out["ftp"]
    assert ftp["confidence"] == "low"
    assert "underestimate" in ftp["note"]


def test_ftp_none_without_power():
    acts = [_act(1, hr=[150.0] * 1200)]
    out = th.estimate_thresholds(acts)
    assert out["ftp"] is None
    assert out["n_power_activities"] == 0


def test_ftp_60min_best_takes_priority():
    acts = [_act(1, power=[240.0] * 3600)] * 3
    out = th.estimate_thresholds(acts)
    assert out["ftp"]["method"] == "60min_best"
    assert out["ftp"]["value"] == 240


# -- LTHR estimation -------------------------------------------------------


def test_lthr_from_20min_hr():
    acts = [_act(i, hr=[160.0] * 1200) for i in range(1, 4)]
    out = th.estimate_thresholds(acts)
    lthr = out["lthr"]
    assert lthr["method"] == "best_20min_hr"
    assert lthr["value"] == 160
    assert lthr["confidence"] == "medium"


def test_lthr_fallback_to_maxhr_when_no_sustained_effort():
    acts = [_act(i, hr=[170.0] * 100) for i in range(1, 4)]
    out = th.estimate_thresholds(acts)
    lthr = out["lthr"]
    assert lthr["method"] == "maxhr*0.90"
    assert lthr["value"] == 153  # 170 * 0.90
    assert lthr["confidence"] == "low"


def test_lthr_never_high():
    # Even with plentiful sustained data, HR estimate caps at medium.
    acts = [_act(i, hr=[165.0] * 1800) for i in range(1, 6)]
    out = th.estimate_thresholds(acts)
    assert out["lthr"]["confidence"] == "medium"


# -- windowing -------------------------------------------------------------


def test_old_activities_excluded_from_default_window():
    acts = [
        _act(5, power=[250.0] * 1200),
        _act(100, power=[300.0] * 1200),  # outside 42d window
    ]
    out = th.estimate_thresholds(acts)
    assert out["window_days"] == 42
    assert out["n_power_activities"] == 1
    assert out["ftp"]["evidence"]["best_20min_w"] == 250


def test_window_widens_to_90d_when_sparse_and_downgrades():
    # Only one activity in 42d (sparse), more within 90d -> widen + downgrade.
    acts = [
        _act(10, power=[250.0] * 1200),
        _act(60, power=[250.0] * 1200),
        _act(80, power=[250.0] * 1200),
    ]
    out = th.estimate_thresholds(acts)
    assert out["window_days"] == 90
    assert out["n_power_activities"] == 3


def test_empty_input():
    out = th.estimate_thresholds([])
    assert out["ftp"] is None
    assert out["lthr"] is None
    assert out["n_power_activities"] == 0
