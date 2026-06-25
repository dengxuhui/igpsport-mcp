"""Tools: create_workout, list_workouts, get_workout_detail, delete_workout."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._service import IGPSportService


def register(server: FastMCP, service: IGPSportService) -> None:
    @server.tool()
    def create_workout(workout_ir: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
        """Create a training workout from an LLM-friendly IR.

        The ``workout_ir`` dict follows the schema documented in
        ``workout/ir.py`` — human units everywhere (seconds, km/h, %FTP,
        BPM, RPM). The server compiles it to iGPSport's native format and
        pushes it so the workout appears in the mobile app.

        Set ``dry_run=True`` to validate + preview the compiled API body
        without sending it.
        """
        return service.create_workout(workout_ir, dry_run=dry_run)

    @server.tool()
    def list_workouts() -> dict[str, Any]:
        """List all custom workouts from iGPSport server (live, not cached)."""
        return service.list_workouts()

    @server.tool()
    def get_workout_detail(workout_id: int) -> dict[str, Any]:
        """Fetch full detail (including structure) of a workout from server."""
        return service.get_workout_detail(workout_id)

    @server.tool()
    def delete_workout(workout_id: int, *, confirm: bool = False) -> dict[str, Any]:
        """Delete a custom workout from the iGPSport server.

        Destructive and irreversible. Defaults to a dry preview that asks for
        confirmation; pass ``confirm=True`` to actually delete.
        """
        return service.delete_workout(workout_id, confirm=confirm)
