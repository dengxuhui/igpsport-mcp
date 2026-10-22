"""Gear tools for CN and international accounts. Reads are live; images stay private."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from ..gear.models import BikeChanges, BikeCreate
from ._service import IGPSportService


def register(server: FastMCP, service: IGPSportService) -> None:
    @server.tool()
    def list_bikes(
        status: Literal["active", "retired", "all"] = "active", limit: int = 20, offset: int = 0
    ) -> dict[str, Any]:
        """List live bikes (CN and international), with kilometre/kg/mm units."""
        return service.gear.list_bikes(status, limit, offset)

    @server.tool()
    def get_bike(bike_id: str) -> dict[str, Any]:
        """Find a bike across active and retired equipment."""
        return service.gear.get_bike(bike_id)

    @server.tool()
    def get_bike_options() -> dict[str, Any]:
        """Return preset bike type and frame size IDs and labels."""
        return service.gear.get_bike_options()

    @server.tool()
    def create_bike(bike: BikeCreate, dry_run: bool = False) -> dict[str, Any]:
        """Create a bike; preview with dry_run. Use kg, km and mm.

        bike_type/frame_size accept preset integer IDs or custom text.
        Defaults: current UTC year, M, 175 mm cranks, zero mileage and
        maintenance, tracking now, non-default, non-retired.
        """
        return service.gear.create_bike(bike, dry_run)

    @server.tool()
    def update_bike(bike_id: str, changes: BikeChanges, dry_run: bool = False) -> dict[str, Any]:
        """Merge supplied fields into freshly read bike data. Omit unchanged fields.

        Units: kg, km, mm. maintenance_interval_km=0 disables maintenance.
        dry_run previews without writing. Concurrent edits cannot be atomic.
        """
        return service.gear.update_bike(bike_id, changes, dry_run)

    @server.tool()
    def set_default_bike(bike_id: str) -> dict[str, Any]:
        """Make an active bike the default; refresh all bike flags."""
        return service.gear.set_default_bike(bike_id)

    @server.tool()
    def set_bike_retired(bike_id: str, retired: bool) -> dict[str, Any]:
        """Retire or unretire a bike, refreshing default-selection side effects."""
        return service.gear.set_bike_retired(bike_id, retired)

    @server.tool()
    def reset_bike_odometer(bike_id: str) -> dict[str, Any]:
        """Reset Current Odometer only; preserve initial and total mileage."""
        return service.gear.reset_bike_odometer(bike_id)

    @server.tool()
    def delete_bike(bike_id: str, confirm: bool = False) -> dict[str, Any]:
        """Preview permanent deletion; requires retirement and confirm=true to delete."""
        return service.gear.delete_bike(bike_id, confirm)

    @server.tool()
    def get_activity_bike(ride_id: int) -> dict[str, Any] | None:
        """Return the live activity bike assignment, or null if unassigned."""
        return service.gear.get_activity_bike(ride_id)

    @server.tool()
    def set_activity_bike(ride_id: int, bike_id: str | None) -> dict[str, Any]:
        """Assign/reassign an activity to an active bike, or pass null to unassign.

        Uses fresh raw activity distance and exact start time. Matching assignments
        perform no write. Writes are never automatically replayed.
        """
        return service.gear.set_activity_bike(ride_id, bike_id)
