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
    # queryMyActivity has no power/HR; the keys must be absent (not null), else
    # the LLM reads them as "no sensor". Per-ride power/HR is in get_activity_summary.
    out = norm.to_list_output(norm.normalize_list_row(_ROW))
    assert "avg_power_w" not in out
    assert "avg_hr_bpm" not in out
    assert set(out) == {
        "ride_id",
        "name",
        "start_time",
        "duration_s",
        "distance_km",
        "elevation_gain_m",
        "avg_speed_kmh",
    }


def test_list_output_includes_avg_speed():
    row = {**_ROW, "avgSpeed": 7.5}  # m/s
    out = norm.to_list_output(norm.normalize_list_row(row))
    assert out["avg_speed_kmh"] == 27.0
    # Missing avgSpeed degrades to None, not a crash.
    assert norm.to_list_output(norm.normalize_list_row(_ROW))["avg_speed_kmh"] is None


def test_cache_row_serializes_raw():
    row = norm.to_cache_row(norm.normalize_list_row(_ROW))
    assert row["sport_type"] == "cycling"
    assert row["raw_json"] == _ROW


_STATS = {
    "axis": [
        {
            "alias": "1",
            "time": "2026/01",
            "totalCount": 22,
            "totalTimerTime": 76515.0,
            "value": 572.5,
        },
        {"alias": "7", "group": "7", "time": "2026/07", "value": 0.0},
    ],
    "milestoneList": [{"count": 135, "distance": "10"}, {"count": 14, "distance": "100"}],
    "personalBestList": [
        {
            "activityId": 47721422,
            "keyLabel": "最远距离",
            "keyName": "MaxDistance",
            "keyTime": "2026-04-25 08:53:11",
            "keyValue": "178207.23",
            "memberId": "1445753",
        },
        {
            "activityId": 50018078,
            "keyLabel": "最快平均速度",
            "keyName": "MaxAvgSpeed",
            "keyTime": "2026-06-01 18:54:37",
            "keyValue": "8.685",
            "memberId": "1445753",
        },
        {
            "activityId": 45881240,
            "keyLabel": "最大功率",
            "keyName": "MaxMaxPower",
            "keyTime": "2026-03-22 09:15:21",
            "keyValue": "851",
            "memberId": "1445753",
        },
    ],
    "statisticsData": {
        "avgSpeed": 7.4832234,
        "sumTotalAscent": 19748.0,
        "totalCalories": 96834,
        "totalCount": 138,
        "totalDistance": 4340509.0,
        "totalPwrTSS": 9613.5,
        "totalTimerTime": 580032,
    },
}


def test_normalize_member_statistics_totals_and_units():
    out = norm.normalize_member_statistics(_STATS)
    totals = out["totals"]
    assert totals["ride_count"] == 138
    assert totals["distance_km"] == 4340.51
    assert totals["duration_h"] == 161.12
    assert totals["avg_speed_kmh"] == 26.94
    assert totals["tss"] == 9613.5


def test_normalize_member_statistics_axis_and_milestones():
    out = norm.normalize_member_statistics(_STATS)
    jan = out["monthly"][0]
    assert jan["period"] == "2026/01"
    assert jan["distance_km"] == 572.5
    assert jan["ride_count"] == 22
    assert jan["duration_h"] == 21.25
    # Future, empty month: no count/timer.
    assert out["monthly"][1]["ride_count"] is None
    assert out["milestones"][0] == {"distance_km": 10, "ride_count": 135}


def test_normalize_personal_best_unit_conversion():
    out = norm.normalize_member_statistics(_STATS)
    pbs = {pb["metric"]: pb for pb in out["personal_bests"]}
    assert pbs["MaxDistance"]["value"] == 178.21
    assert pbs["MaxDistance"]["unit"] == "km"
    assert pbs["MaxDistance"]["ride_id"] == "47721422"
    assert pbs["MaxDistance"]["achieved_at"] == "2026-04-25T08:53:11+08:00"
    assert pbs["MaxAvgSpeed"]["value"] == 31.27  # 8.685 m/s -> km/h
    assert pbs["MaxMaxPower"]["value"] == 851
    assert pbs["MaxMaxPower"]["unit"] == "W"
