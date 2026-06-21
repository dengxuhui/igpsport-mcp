import math

import numpy as np
import pytest

from igpsport_mcp.analysis import power


def test_np_of_constant_power_equals_that_power():
    # Constant power for >30s: every 30s rolling avg == P, so NP == P.
    np_value = power.normalized_power([200.0] * 300)
    assert np_value == pytest.approx(200.0, rel=1e-9)


def test_np_none_when_fewer_than_30_samples():
    assert power.normalized_power([200.0] * 29) is None
    assert power.normalized_power([]) is None


def test_np_weights_high_power_more_than_mean():
    # Alternating load: NP must exceed the arithmetic mean (quartic weighting).
    series = ([100.0] * 60 + [300.0] * 60) * 5
    np_value = power.normalized_power(series)
    assert np_value is not None
    assert np_value > float(np.mean(series))


def test_np_hand_computed_two_levels():
    # 60s @100 then 60s @300. After warmup the 30s-avg is 100, ramps to 300,
    # then 300; NP = (mean(avg^4))^0.25. Compare to a direct pandas computation.
    import pandas as pd

    series = [100.0] * 60 + [300.0] * 60
    rolling = pd.Series(series).rolling(30, min_periods=30).mean().dropna()
    expected = float((rolling**4).mean() ** 0.25)
    assert power.normalized_power(series) == pytest.approx(expected, rel=1e-12)


def test_intensity_factor():
    assert power.intensity_factor(250.0, 250.0) == pytest.approx(1.0)
    assert power.intensity_factor(200.0, 250.0) == pytest.approx(0.8)
    assert power.intensity_factor(200.0, 0) is None


def test_tss_one_hour_at_ftp_is_100():
    # 1h at NP=FTP -> IF=1.0 -> TSS=100 by definition.
    ftp = 250.0
    if_ = power.intensity_factor(ftp, ftp)
    assert power.training_stress_score(3600, ftp, if_, ftp) == pytest.approx(100.0)


def test_tss_two_hours_at_70pct():
    ftp = 250.0
    np_w = 175.0  # 0.7 * FTP
    if_ = power.intensity_factor(np_w, ftp)
    tss = power.training_stress_score(7200, np_w, if_, ftp)
    assert tss == pytest.approx(2 * 100 * 0.7**2, rel=1e-9)  # 98.0


def test_work_kj_at_1hz():
    # 100 W for 3600 s = 360000 J = 360 kJ.
    assert power.work_kj([100.0] * 3600) == pytest.approx(360.0)
    assert power.work_kj([]) is None


def test_work_kj_ignores_nan():
    assert power.work_kj([100.0, math.nan, 100.0]) == pytest.approx(0.2)


def test_power_zones_partition_and_boundaries():
    ftp = 100.0  # so watts == %FTP, boundaries land on integers
    # one sample squarely inside each of z1..z7
    samples = [10, 60, 80, 100, 110, 130, 200]
    zones = power.power_zone_seconds(samples, ftp)
    assert zones == {"z1": 1, "z2": 1, "z3": 1, "z4": 1, "z5": 1, "z6": 1, "z7": 1}
    assert sum(zones.values()) == len(samples)


def test_power_zones_ignores_nan_and_requires_ftp():
    assert power.power_zone_seconds([100.0, math.nan], None) is None
    zones = power.power_zone_seconds([10.0, math.nan, 200.0], 100.0)
    assert sum(zones.values()) == 2
