import math

import pytest

from igpsport_mcp.analysis import hr


def test_hr_tss_one_hour_at_lthr_is_100():
    assert hr.hr_tss(3600, 160.0, 160.0) == pytest.approx(100.0)


def test_hr_tss_scales_with_duration_and_ratio_squared():
    # 2h at 0.8*LTHR -> 2 * 100 * 0.64 = 128.
    assert hr.hr_tss(7200, 128.0, 160.0) == pytest.approx(128.0, rel=1e-9)


def test_hr_tss_guards():
    assert hr.hr_tss(3600, 160.0, 0) is None
    assert hr.hr_tss(3600, 0, 160.0) is None


def test_hr_zones_boundaries():
    lthr = 100.0  # bpm == %LTHR
    # one sample inside each Friel zone z1..z5
    samples = [50, 85, 91, 96, 105]
    zones = hr.hr_zone_seconds(samples, lthr)
    assert zones == {"z1": 1, "z2": 1, "z3": 1, "z4": 1, "z5": 1}
    assert sum(zones.values()) == len(samples)


def test_hr_zones_requires_lthr_and_ignores_nan():
    assert hr.hr_zone_seconds([100.0], None) is None
    zones = hr.hr_zone_seconds([50.0, math.nan, 105.0], 100.0)
    assert zones["z1"] == 1 and zones["z5"] == 1
    assert sum(zones.values()) == 2
