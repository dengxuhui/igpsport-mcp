import pytest

from igpsport_mcp.config import load_config
from igpsport_mcp.storage import db as db_mod
from igpsport_mcp.tools._service import IGPSportService


class FakeClient:
    def __init__(self, pages=None, fit_path=None):
        self._pages = pages or []
        self._fit_path = fit_path

    def list_activities(self, page_no, page_size):
        idx = page_no - 1
        return self._pages[idx] if 0 <= idx < len(self._pages) else []

    def download_fit(self, ride_id):
        return self._fit_path


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
