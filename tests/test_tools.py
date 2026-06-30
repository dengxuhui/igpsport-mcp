import asyncio

from igpsport_mcp.config import load_config
from igpsport_mcp.server import build_server

EXPECTED_TOOLS = {
    "list_activities",
    "get_activity_summary",
    "get_activity_streams",
    "get_activity_laps",
    "get_athlete_profile",
    "get_athlete_stats",
    "get_member_statistics",
    "estimate_thresholds",
    "compare_activities",
    "analyze_training_load",
    "list_segments_collected",
    "get_segment_detail",
    "get_segment_rank",
    "create_workout",
    "list_workouts",
    "get_workout_detail",
    "delete_workout",
}


def test_all_tools_registered():
    server = build_server(load_config({}))
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == EXPECTED_TOOLS


class _StubWorkoutClient:
    """Records server-side workout calls without touching the network."""

    def __init__(self) -> None:
        self.created: dict | None = None
        self.deleted: list[int] = []
        self._workouts: dict[int, dict] = {
            4242: {"title": "2x20 SST", "totalTime": 3600},
        }

    def list_workouts(self) -> list[dict]:
        return [
            {"id": wid, "title": w["title"], "totalTime": w["totalTime"], "img": "", "grade": 0}
            for wid, w in self._workouts.items()
        ]

    def create_workout(self, data: dict) -> dict:
        self.created = data
        wid = 4242
        self._workouts[wid] = {"title": "2x20 SST", "totalTime": 3600}
        return {"workoutId": wid}

    def get_workout_detail(self, workout_id: int) -> dict:
        return self._workouts.get(workout_id, {})

    def delete_workout(self, workout_id: int) -> None:
        self.deleted.append(workout_id)
        self._workouts.pop(workout_id, None)


def _workout_service(tmp_path):
    from igpsport_mcp.storage import db as db_mod
    from igpsport_mcp.tools._service import IGPSportService

    conn = db_mod.connect(tmp_path / "wo.db")
    client = _StubWorkoutClient()
    service = IGPSportService(load_config({"IGPSPORT_FTP": "250"}), client=client, db_conn=conn)
    return service, client


_SIMPLE_IR = {
    "title": "2x20 SST",
    "steps": [
        {
            "name": "Warmup",
            "intensity": "warmup",
            "duration": {"type": "time", "value": 600},
        }
    ],
}


def test_create_workout_dry_run_does_not_send(tmp_path):
    service, client = _workout_service(tmp_path)
    out = service.create_workout(_SIMPLE_IR, dry_run=True)
    assert out["success"] and out["dry_run"]
    assert client.created is None  # nothing sent


def test_create_workout_invalid_ir_returns_errors(tmp_path):
    service, client = _workout_service(tmp_path)
    out = service.create_workout({"title": "", "steps": []}, dry_run=True)
    assert out["success"] is False and out["errors"]
    assert client.created is None


def test_create_workout_with_calendar_dry_run(tmp_path):
    service, client = _workout_service(tmp_path)
    out = service.create_workout(_SIMPLE_IR, dry_run=True, with_calendar=True)
    assert client.created is None
    cal = out["calendar"]
    assert cal["title"] == "2x20 SST"
    assert "DTSTART;VALUE=DATE:{{SCHEDULED_DATE}}" in cal["ical"]


def test_create_workout_calendar_is_opt_in(tmp_path):
    service, _ = _workout_service(tmp_path)
    out = service.create_workout(_SIMPLE_IR, dry_run=True)
    assert "calendar" not in out


def test_list_workouts_from_server(tmp_path):
    service, _ = _workout_service(tmp_path)
    result = service.list_workouts()
    assert result["total"] == 1
    assert result["workouts"][0]["workout_id"] == 4242
    assert result["workouts"][0]["title"] == "2x20 SST"


def test_create_then_delete_workout_with_confirmation(tmp_path):
    service, client = _workout_service(tmp_path)

    created = service.create_workout(_SIMPLE_IR)
    assert created == {"success": True, "workout_id": 4242}
    assert client.created is not None

    # Without confirm: preview only, nothing deleted.
    preview = service.delete_workout(4242)
    assert preview["requires_confirmation"] is True
    assert preview["title"] == "2x20 SST"
    assert client.deleted == []

    # With confirm: server delete succeeds.
    done = service.delete_workout(4242, confirm=True)
    assert done["success"] is True
    assert client.deleted == [4242]


def test_call_tool_through_server_network_free(monkeypatch):
    # get_athlete_profile now also reads weight/maxHR from the server; stub that
    # out so this exercises the full tool wiring (FastMCP -> wrapper -> service)
    # without any network, while FTP/LTHR still come from config.
    from igpsport_mcp.tools._service import IGPSportService

    monkeypatch.setattr(IGPSportService, "_member_info", lambda self: None)
    server = build_server(load_config({"IGPSPORT_FTP": "250", "IGPSPORT_LTHR": "160"}))
    _content, structured = asyncio.run(server.call_tool("get_athlete_profile", {}))
    assert structured["ftp_w"] == 250
    assert structured["lthr_bpm"] == 160
    assert structured["power_zones"]["z1"] == [0.0, 137.5]
