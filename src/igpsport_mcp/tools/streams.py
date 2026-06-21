"""Tool: get_activity_streams (forced downsampling + channel select)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._service import IGPSportService


def register(server: FastMCP, service: IGPSportService) -> None:
    @server.tool()
    def get_activity_streams(
        ride_id: str,
        channels: list[str] | None = None,
        resolution: str = "10s",
        start_offset_s: int = 0,
        end_offset_s: int | None = None,
    ) -> dict[str, Any]:
        """Time-series channels as compact bare arrays. Channels default to power+hr;
        resolution one of 1s/5s/10s/30s/1min (default 10s to keep tokens sane)."""
        return service.get_activity_streams(
            ride_id, channels, resolution, start_offset_s, end_offset_s
        )
