"""Tools: list_segments, get_segment_detail, get_segment_rank."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._service import IGPSportService


def register(server: FastMCP, service: IGPSportService) -> None:
    @server.tool()
    def list_segments_collected(
        page_no: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """List your collected (starred) segments with best times."""
        return service.list_segments_collected(page_no, page_size)

    @server.tool()
    def get_segment_detail(segments_id: str) -> dict[str, Any]:
        """Segment detail: name, distance, grade, KOM, fastest times & your PR."""
        return service.get_segment_detail(segments_id)

    @server.tool()
    def get_segment_rank(
        segments_id: str,
        page_no: int = 1,
        page_size: int = 30,
        query_type: int = 1,
    ) -> dict[str, Any]:
        """Segment leaderboard. queryType: 1=all-time, 2=yearly (or other dim)."""
        return service.get_segment_rank(segments_id, page_no, page_size, query_type)
