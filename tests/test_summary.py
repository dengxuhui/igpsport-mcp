from datetime import UTC, datetime, timedelta

import pytest

from igpsport_mcp.analysis.summary import build_summary
from igpsport_mcp.fit.parser import ParsedActivity


def _constant_activity(seconds=120, watts=200, hr=150):
    base = datetime(2026, 6, 19, 8, 0, 0, tzinfo=UTC)
    records = [
        {
            "timestamp": base + timedelta(seconds=i),
            "power": watts,
            "heart_rate": hr,
            "cadence": 90,
            "speed": 10.0,  # m/s
            "temperature": 22,
        }
        for i in range(seconds)
    ]
    session = {
        "start_time": base,
        "total_timer_time": seconds,
        "total_distance": 4000,
        "total_ascent": 30,
        "total_descent": 25,
        "avg_power": watts,
        "max_power": watts,
        "avg_heart_rate": hr,
        "max_heart_rate": hr,
        "avg_cadence": 90,
        "avg_speed": 10.0,
        "max_speed": 12.0,
        "avg_temperature": 22,
    }
    return ParsedActivity(records=records, laps=[], session=session)


def test_build_summary_constant_power():
    parsed = _constant_activity()
    out = build_summary(parsed, ftp_w=250, lthr_bpm=160)
    s = out["summary"]

    assert out["duration_s"] == 120
    assert out["start_time"].startswith("2026-06-19T08:00:00")
    assert s["normalized_power_w"] == pytest.approx(200.0, rel=1e-6)
    assert s["intensity_factor"] == pytest.approx(0.8, rel=1e-6)
    assert s["tss"] == pytest.approx(2.1, abs=0.1)
    assert s["work_kj"] == pytest.approx(24.0, rel=1e-6)
    assert s["distance_km"] == 4.0
    assert s["avg_speed_kmh"] == pytest.approx(36.0)
    assert out["tss_estimated_from_hr"] is False
    # 200W == 0.8*FTP -> Coggan z3; 150bpm == 0.9375*LTHR -> Friel z3
    assert out["power_zones_s"]["z3"] > 0
    assert out["hr_zones_s"]["z3"] > 0


def test_build_summary_no_power_uses_hr_tss():
    parsed = _constant_activity()
    for rec in parsed.records:
        del rec["power"]
    parsed.session.pop("avg_power")
    parsed.session.pop("max_power")

    out = build_summary(parsed, ftp_w=250, lthr_bpm=160)
    assert out["summary"]["normalized_power_w"] is None
    assert out["summary"]["tss"] is not None
    assert out["tss_estimated_from_hr"] is True
    assert out["power_zones_s"] is None


def test_build_summary_without_ftp_lthr():
    out = build_summary(_constant_activity(), ftp_w=None, lthr_bpm=None)
    assert out["summary"]["tss"] is None
    assert out["summary"]["intensity_factor"] is None
    assert out["power_zones_s"] is None
    assert out["hr_zones_s"] is None
    # NP/work don't need FTP and should still compute.
    assert out["summary"]["normalized_power_w"] == pytest.approx(200.0)
