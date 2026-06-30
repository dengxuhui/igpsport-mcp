"""MCP tool layer. ``register_all`` wires the 17 tools onto the FastMCP server."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from ._service import IGPSportService


def register_all(server: FastMCP, service: IGPSportService) -> None:
    from . import activities, athlete, compare, laps, segments, streams, training_load, workouts

    for module in (activities, streams, laps, athlete, compare, training_load, segments, workouts):
        module.register(server, service)
