from igpsport_mcp.storage import db


def _conn(tmp_path):
    return db.connect(tmp_path / "activities.db")


def test_connect_creates_schema(tmp_path):
    conn = _conn(tmp_path)
    tables = {
        row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"activities", "activity_metrics", "athlete_profile"} <= tables


def test_upsert_and_get(tmp_path):
    conn = _conn(tmp_path)
    db.upsert_activity(
        conn,
        {
            "ride_id": 123,
            "name": "morning ride",
            "start_time": "2026-06-19",
            "distance_km": 100.0,
            "raw_json": {"rideId": 123, "title": "morning ride"},
        },
    )
    got = db.get_activity(conn, 123)
    assert got is not None
    assert got["ride_id"] == "123"
    assert got["distance_km"] == 100.0
    assert '"rideId": 123' in got["raw_json"]
    assert got["fetched_at"]  # auto-stamped


def test_upsert_is_idempotent_update(tmp_path):
    conn = _conn(tmp_path)
    db.upsert_activity(conn, {"ride_id": 1, "name": "a", "start_time": "2026-01-01"})
    db.upsert_activity(conn, {"ride_id": 1, "name": "b", "start_time": "2026-01-01"})
    assert db.get_activity(conn, 1)["name"] == "b"
    assert len(db.list_activities(conn)) == 1


def test_list_orders_by_start_time_desc(tmp_path):
    conn = _conn(tmp_path)
    db.upsert_activities(
        conn,
        [
            {"ride_id": 1, "start_time": "2026-01-01"},
            {"ride_id": 2, "start_time": "2026-03-01"},
            {"ride_id": 3, "start_time": "2026-02-01"},
        ],
    )
    rows = db.list_activities(conn, limit=2)
    assert [r["ride_id"] for r in rows] == ["2", "3"]


def test_set_fit_path(tmp_path):
    conn = _conn(tmp_path)
    db.upsert_activity(conn, {"ride_id": 9, "start_time": "2026-01-01"})
    db.set_fit_path(conn, 9, tmp_path / "fit" / "9.fit")
    assert db.get_activity(conn, 9)["fit_path"].endswith("9.fit")
