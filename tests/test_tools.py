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
    "compare_activities",
    "analyze_training_load",
    "list_segments_collected",
    "get_segment_detail",
    "get_segment_rank",
}


def test_all_tools_registered():
    server = build_server(load_config({}))
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == EXPECTED_TOOLS


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
