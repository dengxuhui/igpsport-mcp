"""Tools: get_athlete_profile, get_athlete_stats."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._service import IGPSportService


def register(server: FastMCP, service: IGPSportService) -> None:
    @server.tool()
    def get_athlete_profile() -> dict[str, Any]:
        """Athlete training parameters (FTP/LTHR from config) with HR/power zone bounds."""
        return service.get_athlete_profile()

    @server.tool()
    def get_athlete_stats(period: str = "month", end_date: str | None = None) -> dict[str, Any]:
        """Aggregate distance/duration/elevation over week|month|year|all."""
        return service.get_athlete_stats(period, end_date)
