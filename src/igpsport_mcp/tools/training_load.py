"""Tool: analyze_training_load (CTL/ATL/TSB trend, the killer query)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._service import IGPSportService


def register(server: FastMCP, service: IGPSportService) -> None:
    @server.tool()
    def analyze_training_load(days: int = 90, end_date: str | None = None) -> dict[str, Any]:
        """CTL/ATL/TSB daily trend + current form interpretation over the last N days."""
        return service.analyze_training_load(days, end_date)
