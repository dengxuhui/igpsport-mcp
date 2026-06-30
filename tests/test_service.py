import pandas as pd
import pytest

from igpsport_mcp.config import load_config
from igpsport_mcp.storage import db as db_mod
from igpsport_mcp.tools import _service as service_mod
from igpsport_mcp.tools._service import IGPSportService


class FakeClient:
    def __init__(self, pages=None, fit_path=None, member_stats=None):
        self._pages = pages or []
        self._fit_path = fit_path
        self._member_stats = member_stats
        self.member_stats_calls = []

    def list_activities(self, page_no, page_size):
        idx = page_no - 1
        return self._pages[idx] if 0 <= idx < len(self._pages) else []

    def download_fit(self, ride_id):
        return self._fit_path

    def get_member_statistics(self, *, time, stat_type=2, big_sport_type=-1):
        self.member_stats_calls.append((time, stat_type, big_sport_type))
        return self._member_stats


def _client_with_interval(interval_info, **kw):
    """A FakeClient that also exposes get_user_interval_info (call-counted)."""

    client = FakeClient(**kw)
    client.interval_info_calls = 0

    def get_user_interval_info():
        client.interval_info_calls += 1
        return interval_info

    client.get_user_interval_info = get_user_interval_info
    return client


def _raw(ride_id, day, dist_m=100000, asc=800, dur=12600):
    return {
        "rideId": ride_id,
        "title": f"ride {ride_id}",
        "startTime": day,
        "rideDistance": dist_m,
        "totalAscent": asc,
        "totalMovingTime": dur,
        "exerciseType": 0,
    }


def _service(tmp_path, client, **env):
    cfg = load_config({"IGPSPORT_CACHE_DIR": str(tmp_path), **env})
    conn = db_mod.connect(tmp_path / "activities.db")
    return IGPSportService(cfg, client=client, db_conn=conn)


def test_list_activities_normalizes_and_filters(tmp_path):
    pages = [[_raw(1, "2026.06.19"), _raw(2, "2026.05.01"), _raw(3, "2026.06.10")]]
    svc = _service(tmp_path, FakeClient(pages=pages))
    out = svc.list_activities(start_date="2026-06-01", end_date="2026-06-30", limit=20)
    ids = [a["ride_id"] for a in out["activities"]]
    assert ids == ["1", "3"]  # ride 2 filtered out by date
    assert out["total"] == 2
    assert out["activities"][0]["distance_km"] == 100.0


def test_list_activities_pages_past_capped_pages(tmp_path):
    # Server caps each page at 2 rows (< requested). The old "short page = end"
    # heuristic stopped after June; the fix must keep paging back to the floor.
    pages = [
        [_raw(1, "2026.06.19"), _raw(2, "2026.06.10")],
        [_raw(3, "2026.05.20"), _raw(4, "2026.04.15")],
        [_raw(5, "2026.03.30"), _raw(6, "2026.02.01")],
    ]
    svc = _service(tmp_path, FakeClient(pages=pages))
    out = svc.list_activities(start_date="2026-03-01", end_date="2026-06-30", limit=100)
    ids = [a["ride_id"] for a in out["activities"]]
    assert ids == ["1", "2", "3", "4", "5"]  # Feb (ride 6) is before the floor
    assert out["total"] == 5


def test_list_activities_caches_to_db(tmp_path):
    svc = _service(tmp_path, FakeClient(pages=[[_raw(7, "2026.06.19")]]))
    svc.list_activities(limit=10)
    cached = db_mod.get_activity(svc.db, 7)
    assert cached is not None and cached["sport_type"] == "cycling"


def test_get_athlete_profile_from_config(tmp_path):
    svc = _service(tmp_path, FakeClient(), IGPSPORT_FTP="250", IGPSPORT_LTHR="160")
    prof = svc.get_athlete_profile()
    assert prof["ftp_w"] == 250
    assert prof["lthr_bpm"] == 160
    assert prof["power_zones"]["z4"] == [225.0, 262.5]  # [0.90, 1.05] * FTP
    assert prof["power_zones"]["z1"] == [0.0, 137.5]
    assert prof["hr_zones"]["z5"][1] is None


def test_get_athlete_profile_without_params(tmp_path):
    svc = _service(tmp_path, FakeClient())
    prof = svc.get_athlete_profile()
    assert prof["ftp_w"] is None
    assert prof["power_zones"] is None


_INTERVAL = {
    "member": {
        "nickName": "Aerxuhui",
        "ftp": 233,
        "lthr": 171,
        "mhr": 190,
        "weight": 74.0,
        "height": 177,
    }
}


def test_profile_reads_ftp_lthr_from_igpsport_when_unset(tmp_path):
    client = _client_with_interval(_INTERVAL)
    svc = _service(tmp_path, client)
    prof = svc.get_athlete_profile()
    assert prof["ftp_w"] == 233 and prof["ftp_source"] == "igpsport"
    assert prof["lthr_bpm"] == 171 and prof["lthr_source"] == "igpsport"
    assert prof["max_hr_bpm"] == 190
    assert prof["weight_kg"] == 74.0
    assert prof["height_cm"] == 177
    assert prof["nickname"] == "Aerxuhui"
    assert prof["power_zones"]["z4"] == [209.7, 244.7]  # [0.90, 1.05] * 233


def test_profile_config_overrides_server_ftp(tmp_path):
    client = _client_with_interval(_INTERVAL)
    svc = _service(tmp_path, client, IGPSPORT_FTP="250")
    prof = svc.get_athlete_profile()
    assert prof["ftp_w"] == 250 and prof["ftp_source"] == "config"
    # LTHR not configured -> still filled from the server.
    assert prof["lthr_bpm"] == 171 and prof["lthr_source"] == "igpsport"


def test_profile_enriches_weight_even_when_thresholds_configured(tmp_path):
    # FTP/LTHR overridden by env, but weight / maxHR still come from the server.
    client = _client_with_interval(_INTERVAL)
    svc = _service(tmp_path, client, IGPSPORT_FTP="250", IGPSPORT_LTHR="160")
    prof = svc.get_athlete_profile()
    assert prof["ftp_w"] == 250 and prof["ftp_source"] == "config"
    assert prof["lthr_bpm"] == 160 and prof["lthr_source"] == "config"
    assert prof["weight_kg"] == 74.0
    assert prof["max_hr_bpm"] == 190
    assert client.interval_info_calls == 1


def test_member_info_fetched_once_and_cached(tmp_path):
    client = _client_with_interval(_INTERVAL)
    svc = _service(tmp_path, client)
    svc.get_athlete_profile()
    assert svc._ftp == 233.0
    assert svc._lthr == 171.0
    assert client.interval_info_calls == 1  # cached across all three reads


def test_member_info_failure_degrades_to_none(tmp_path):
    client = FakeClient()

    def boom():
        raise RuntimeError("network down")

    client.get_user_interval_info = boom
    svc = _service(tmp_path, client)
    prof = svc.get_athlete_profile()
    assert prof["ftp_w"] is None and prof["power_zones"] is None


def test_analyze_training_load(tmp_path, monkeypatch):
    pages = [[_raw(1, "2026.06.01"), _raw(2, "2026.06.15"), _raw(3, "2026.06.20")]]
    svc = _service(tmp_path, FakeClient(pages=pages))
    monkeypatch.setattr(svc, "_load_summary", lambda ride_id: {"summary": {"tss": 80.0}})

    out = svc.analyze_training_load(days=30, end_date="2026-06-21")
    assert out["days"] == 30
    assert out["current"] is not None
    assert "Form:" in out["current"]["interpretation"]
    assert len(out["daily"]) > 0
    # CTL should be positive after several 80-TSS days.
    assert out["current"]["ctl"] > 0


def test_analyze_training_load_empty(tmp_path, monkeypatch):
    svc = _service(tmp_path, FakeClient(pages=[[]]))
    out = svc.analyze_training_load(days=30, end_date="2026-06-21")
    assert out["daily"] == []
    assert out["current"] is None


def test_compare_activities(tmp_path, monkeypatch):
    svc = _service(tmp_path, FakeClient())
    summaries = {
        "1": {"summary": {"avg_power_w": 200, "tss": 100}},
        "2": {"summary": {"avg_power_w": 250, "tss": 150}},
    }
    monkeypatch.setattr(svc, "_load_summary", lambda ride_id: summaries[str(ride_id)])

    out = svc.compare_activities(["1", "2"], metrics=["avg_power_w", "tss"])
    power_row = next(c for c in out["comparison"] if c["metric"] == "avg_power_w")
    assert power_row["delta_pct"] == pytest.approx(25.0)  # (250-200)/200
    assert out.get("narrative_hint")


def test_get_athlete_stats(tmp_path):
    pages = [[_raw(1, "2026.06.19", dist_m=50000, dur=3600, asc=500)]]
    svc = _service(tmp_path, FakeClient(pages=pages))
    stats = svc.get_athlete_stats(period="month", end_date="2026-06-21")
    assert stats["ride_count"] == 1
    assert stats["total_distance_km"] == 50.0
    assert stats["total_duration_h"] == 1.0
    assert stats["total_elevation_m"] == 500.0


def test_get_member_statistics(tmp_path):
    payload = {
        "statisticsData": {
            "totalCount": 138,
            "totalDistance": 4340509.0,
            "totalTimerTime": 580032,
            "avgSpeed": 7.4832234,
            "sumTotalAscent": 19748.0,
            "totalCalories": 96834,
            "totalPwrTSS": 9613.5,
        },
        "axis": [{"time": "2026/01", "totalCount": 22, "totalTimerTime": 76515.0, "value": 572.5}],
        "milestoneList": [{"count": 135, "distance": "10"}],
        "personalBestList": [
            {
                "activityId": 47721422,
                "keyName": "MaxDistance",
                "keyLabel": "最远距离",
                "keyTime": "2026-04-25 08:53:11",
                "keyValue": "178207.23",
            }
        ],
    }
    client = FakeClient(member_stats=payload)
    svc = _service(tmp_path, client)
    out = svc.get_member_statistics(time="2026-06-24")
    assert client.member_stats_calls == [("2026-06-24", 2, -1)]
    assert out["time"] == "2026-06-24"
    assert out["stat_type"] == 2
    assert out["totals"]["distance_km"] == 4340.51
    assert out["monthly"][0]["distance_km"] == 572.5
    assert out["personal_bests"][0]["value"] == 178.21


def test_get_member_statistics_defaults_time_to_today(tmp_path):
    client = FakeClient(member_stats={})
    svc = _service(tmp_path, client)
    svc.get_member_statistics()
    assert len(client.member_stats_calls) == 1
    assert client.member_stats_calls[0][1:] == (2, -1)
    # default time is an ISO date string
    assert len(client.member_stats_calls[0][0]) == 10


# --- real-FIT paths (skip without the local fixture) ---


def _service_with_fit(tmp_path, sample_fit):
    return _service(
        tmp_path, FakeClient(fit_path=sample_fit), IGPSPORT_FTP="250", IGPSPORT_LTHR="160"
    )


def test_get_activity_summary_real_fit(tmp_path, sample_fit):
    svc = _service_with_fit(tmp_path, sample_fit)
    out = svc.get_activity_summary("999")
    assert out["ride_id"] == "999"
    assert out["duration_s"] > 0
    assert out["summary"]["distance_km"] > 0


def test_get_activity_streams_real_fit(tmp_path, sample_fit):
    svc = _service_with_fit(tmp_path, sample_fit)
    out = svc.get_activity_streams("999", channels=["power", "hr"], resolution="30s")
    assert out["resolution"] == "30s"
    assert out["sample_count"] > 0
    for payload in out["channels"].values():
        assert "unit" in payload and isinstance(payload["values"], list)
        assert not payload["values"] or not isinstance(payload["values"][0], dict)


def test_get_activity_laps_real_fit(tmp_path, sample_fit):
    svc = _service_with_fit(tmp_path, sample_fit)
    out = svc.get_activity_laps("999")
    assert "laps" in out and isinstance(out["laps"], list)
    if out["laps"]:
        lap = out["laps"][0]
        assert {"lap_index", "duration_s", "distance_km"} <= set(lap)


def test_estimate_thresholds_orchestration(tmp_path, monkeypatch):
    # Two usable rides (a 20-min @250W ride and a 5-min @300W ride) + one whose
    # FIT fails to parse and must be skipped without breaking the rest.
    pages = [[_raw(1, "2026.06.28"), _raw(2, "2026.06.20"), _raw(3, "2026.06.15")]]
    svc = _service(tmp_path, FakeClient(pages=pages))

    class _Parsed:
        def __init__(self, rid):
            self.records = str(rid)

    monkeypatch.setattr(svc, "_parse_fit_cached", lambda rid: _Parsed(rid))

    dfs = {
        "1": pd.DataFrame({"power": [250.0] * 1200, "heart_rate": [160.0] * 1200}),
        "2": pd.DataFrame({"power": [300.0] * 300, "heart_rate": [150.0] * 300}),
    }
    # Ride 3 missing -> KeyError inside the parse/resample block -> skipped.
    monkeypatch.setattr(service_mod, "resample_to_1hz", lambda records: dfs[records])

    out = svc.estimate_thresholds(window_days=42, end_date="2026-06-30")
    assert out["n_power_activities"] == 2  # ride 3 skipped
    assert out["ftp"]["method"] == "20min_best*0.95"
    assert out["ftp"]["evidence"]["best_20min_w"] == 250
    assert out["ftp"]["evidence"]["best_5min_w"] == 300
    assert out["lthr"]["method"] == "best_20min_hr"
    assert out["lthr"]["value"] == 160
