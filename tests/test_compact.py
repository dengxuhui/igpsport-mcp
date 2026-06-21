import math

import pytest

from igpsport_mcp.analysis import compact


def test_resolution_mapping():
    assert compact.resolution_to_seconds("10s") == 10
    assert compact.resolution_to_seconds("1min") == 60
    with pytest.raises(ValueError):
        compact.resolution_to_seconds("2h")


def test_downsample_window_1_passthrough_with_nan_as_none():
    assert compact.downsample([100.0, math.nan, 102.0], 1) == [100, None, 102]


def test_downsample_averages_windows():
    # 6 samples, window 3 -> two windows averaged.
    assert compact.downsample([10, 20, 30, 100, 100, 100], 3) == [20, 100]


def test_downsample_partial_last_window():
    # 5 samples, window 2 -> [avg(1,2), avg(3,4), avg(5)].
    assert compact.downsample([2, 4, 6, 8, 10], 2) == [3, 7, 10]


def test_downsample_all_nan_window_is_none():
    assert compact.downsample([math.nan, math.nan], 2) == [None]


def test_downsample_rejects_zero_window():
    with pytest.raises(ValueError):
        compact.downsample([1, 2, 3], 0)


def test_clean_int_vs_float():
    assert compact._clean(120.0) == 120
    assert isinstance(compact._clean(120.0), int)
    assert compact._clean(120.45) == 120.45
    assert compact._clean(math.nan) is None


def test_to_compact_shape_is_bare_arrays():
    out = compact.to_compact(
        {"power": [100, 200, 300, 400], "hr": [120, 130, 140, 150]}, window_s=2
    )
    assert out == {
        "power": {"unit": "watts", "values": [150, 350]},
        "hr": {"unit": "bpm", "values": [125, 145]},
    }
    # never a list of per-point objects
    assert isinstance(out["power"]["values"], list)
    assert not isinstance(out["power"]["values"][0], dict)


def test_to_compact_unknown_channel_unit_override():
    out = compact.to_compact({"foo": [1, 2]}, window_s=1, units={"foo": "x"})
    assert out["foo"]["unit"] == "x"
