from igpsport_mcp.tools import _normalize as norm

_ROW = {
    "rideId": 12345,
    "title": "户外骑行",
    "startTime": "2026.06.19",
    "rideDistance": 100067.09,
    "totalAscent": 850,
    "totalMovingTime": 12600,
    "exerciseType": 0,
}


def test_normalize_units_and_date():
    item = norm.normalize_list_row(_ROW)
    assert item["ride_id"] == "12345"
    assert item["name"] == "户外骑行"
    assert item["start_time"] == "2026-06-19"
    assert item["distance_km"] == 100.07
    assert item["duration_s"] == 12600
    assert item["elevation_gain_m"] == 850


def test_date_range_filter():
    item = norm.normalize_list_row(_ROW)
    assert norm.matches(item, "2026-06-01", "2026-06-30", "cycling")
    assert not norm.matches(item, "2026-07-01", None, "cycling")
    assert not norm.matches(item, None, "2026-06-18", "cycling")


def test_sport_filter():
    item = norm.normalize_list_row(_ROW)
    assert norm.matches(item, None, None, "cycling")
    assert not norm.matches(item, None, None, "running")


def test_list_output_omits_power_hr():
    out = norm.to_list_output(norm.normalize_list_row(_ROW))
    assert out["avg_power_w"] is None
    assert out["avg_hr_bpm"] is None
    assert set(out) == {
        "ride_id",
        "name",
        "start_time",
        "duration_s",
        "distance_km",
        "elevation_gain_m",
        "avg_power_w",
        "avg_hr_bpm",
    }


def test_cache_row_serializes_raw():
    row = norm.to_cache_row(norm.normalize_list_row(_ROW))
    assert row["sport_type"] == "cycling"
    assert row["raw_json"] == _ROW
