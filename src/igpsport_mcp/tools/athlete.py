"""Tools: get_athlete_profile, get_athlete_stats, get_member_statistics, estimate_thresholds."""

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

    @server.tool()
    def get_member_statistics(
        time: str | None = None,
        stat_type: int = 2,
        big_sport_type: int = -1,
    ) -> dict[str, Any]:
        """Official yearly stats & achievements: totals, per-month distance, milestones, PRs.

        Server-side aggregates (no FIT needed). ``time`` is the anchor date
        YYYY-MM-DD (defaults to today); ``stat_type`` 2 = yearly; ``big_sport_type``
        -1 = all sports.
        """
        return service.get_member_statistics(time, stat_type, big_sport_type)

    @server.tool()
    def estimate_thresholds(window_days: int = 42, end_date: str | None = None) -> dict[str, Any]:
        """Estimate FTP & LTHR from recent rides' mean-max curves, for riders who
        haven't done a formal test.

        Aggregates the power/HR duration peaks across all activities in the window
        (default 42 days, auto-widening to 90 when sparse) and applies authoritative
        methods (Coggan 20-min, critical-power cross-check, Friel HR field test).
        Each estimate carries a confidence level (high/medium/low) plus evidence and
        a "confirm with a formal test" caveat; returns ``None`` for a value the data
        can't support (e.g. FTP without any power data). Read-only — never writes the
        values back to iGPSport; the rider applies them manually.
        """
        return service.estimate_thresholds(window_days, end_date)
