"""Tools: list_activities, get_activity_summary."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._service import IGPSportService


def register(server: FastMCP, service: IGPSportService) -> None:
    @server.tool()
    def list_activities(
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 20,
        offset: int = 0,
        sport_type: str = "cycling",
    ) -> dict[str, Any]:
        """List rides with optional ISO-8601 date range and paging (cached, units fixed)."""
        return service.list_activities(start_date, end_date, limit, offset, sport_type)

    @server.tool()
    def get_activity_summary(ride_id: str) -> dict[str, Any]:
        """Derived metrics for one ride: NP/IF/TSS/work, HR & power zone time."""
        return service.get_activity_summary(ride_id)
