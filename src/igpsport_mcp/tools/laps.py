"""Tool: get_activity_laps."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._service import IGPSportService


def register(server: FastMCP, service: IGPSportService) -> None:
    @server.tool()
    def get_activity_laps(ride_id: str) -> dict[str, Any]:
        """Per-lap splits with per-lap NP computed from the record stream."""
        return service.get_activity_laps(ride_id)
