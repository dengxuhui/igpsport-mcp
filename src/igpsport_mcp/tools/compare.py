"""Tool: compare_activities."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._service import IGPSportService


def register(server: FastMCP, service: IGPSportService) -> None:
    @server.tool()
    def compare_activities(ride_ids: list[str], metrics: list[str] | None = None) -> dict[str, Any]:
        """Compare 2-5 rides across metrics with per-metric delta% and a narrative hint."""
        return service.compare_activities(ride_ids, metrics)
