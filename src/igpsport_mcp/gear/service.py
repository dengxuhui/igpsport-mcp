"""Validation, full-save construction and conservative mutation verification."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal, TypeVar

import httpx
from pydantic import BaseModel, TypeAdapter, ValidationError

from ..exceptions import IGPSportAPIChangedError
from .models import Activity, BikeChanges, BikeCreate, Equipment, EquipmentPage, Lookup

T = TypeVar("T")


def _parse(model: type[T], data: Any) -> T:
    try:
        return TypeAdapter(model).validate_python(data)
    except ValidationError as exc:
        raise IGPSportAPIChangedError(
            "Unexpected gear response; please report API drift on GitHub"
        ) from exc


def _public(bike: Equipment) -> dict[str, Any]:
    return {
        "bike_id": bike.id,
        "brand": bike.equipmentBrand,
        "model": bike.equipmentName,
        "bike_type": bike.typeName,
        "bike_type_id": bike.typeId,
        "year": bike.year,
        "frame_size": bike.size,
        "frame_size_id": bike.sizeId,
        "weight_kg": bike.bikeWeight / 1000,
        "wheel_circumference_mm": bike.wheelSize,
        "crank_length_mm": bike.crankLength,
        "initial_mileage_km": (bike.initialMileage or 0) / 1000,
        "total_mileage_km": bike.equipmentMileage / 1000,
        "current_odometer_km": bike.periodMileage / 1000,
        "maintenance_interval_km": (bike.maintainMileage or 0) / 1000,
        "connected_activities_count": bike.connectedActivitiesNumber,
        "tracking_started_at": datetime.fromtimestamp(
            bike.launchedTimestamp / 1000, UTC
        ).isoformat(),
        "is_default": bool(bike.isActivated),
        "is_retired": bool(bike.isRetired),
    }


class GearService:
    def __init__(self, client: Any) -> None:
        self.client = client

    def _scan(self, status: str = "all") -> list[Equipment]:
        collected: list[Equipment] = []
        for retired in [False, True] if status == "all" else [status == "retired"]:
            seen: set[str] = set()
            for page in range(1, 10001):
                result = _parse(EquipmentPage, self.client.list_equipment(retired, page, 20))
                if not result.items:
                    break
                ids = {b.id for b in result.items}
                if ids & seen:
                    raise IGPSportAPIChangedError(
                        "Equipment pagination repeated IDs; scan incomplete"
                    )
                seen.update(ids)
                collected.extend(b for b in result.items if b.equipmentType == 0)
                if len(seen) >= result.total:
                    break
            else:
                raise IGPSportAPIChangedError("Equipment pagination exceeded safety limit")
        return collected

    def list_bikes(
        self,
        status: Literal["active", "retired", "all"] = "active",
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        if status not in {"active", "retired", "all"} or not 1 <= limit <= 100 or offset < 0:
            raise ValueError("Use active/retired/all, limit 1-100 and offset >= 0")
        bikes = self._scan(status)
        return {
            "bikes": [_public(b) for b in bikes[offset : offset + limit]],
            "total": len(bikes),
            "has_more": offset + limit < len(bikes),
        }

    def _find(self, bike_id: str) -> Equipment:
        if not bike_id.strip():
            raise ValueError("bike_id must not be empty")
        matches = [b for b in self._scan() if b.id == bike_id]
        if len(matches) != 1:
            raise ValueError(f"Bike not found uniquely: {bike_id}")
        return matches[0]

    def get_bike(self, bike_id: str) -> dict[str, Any]:
        return _public(self._find(bike_id))

    def get_bike_options(self) -> dict[str, Any]:
        return {
            "bike_types": [
                v.model_dump() for v in _parse(list[Lookup], self.client.get_equipment_types())
            ],
            "frame_sizes": [
                v.model_dump() for v in _parse(list[Lookup], self.client.get_equipment_sizes())
            ],
        }

    def _choice(self, value: int | str, size: bool = False) -> dict[str, Any]:
        label, key = ("size", "sizeId") if size else ("typeName", "typeId")
        if isinstance(value, int):
            options = self.get_bike_options()["frame_sizes" if size else "bike_types"]
            match = next((v for v in options if v["id"] == value and value != 999), None)
            if match is None:
                raise ValueError("Unknown preset ID; use custom text for Other")
            return {key: value, label: match["name"]}
        if not value.strip() or (not size and len(value) > 14):
            raise ValueError("Custom bike types must contain 1-14 characters")
        return {key: 999, label: value}

    def _merge(self, body: dict[str, Any], changes: BaseModel) -> dict[str, Any]:
        values = changes.model_dump(exclude_unset=True)
        if any(v is None for v in values.values()):
            raise ValueError("Omit unchanged fields; use 0 to disable maintenance")
        for key, value in values.items():
            if key in {"bike_type", "frame_size"}:
                body.update(self._choice(value, key == "frame_size"))
            elif key == "year":
                body["year"] = str(value)
            else:
                mapping = {
                    "brand": ("equipmentBrand", 1),
                    "model": ("equipmentName", 1),
                    "weight_kg": ("bikeWeight", 1000),
                    "wheel_circumference_mm": ("wheelSize", 1),
                    "crank_length_mm": ("crankLength", 1),
                    "initial_mileage_km": ("initialMileage", 1000),
                    "current_odometer_km": ("periodMileage", 1000),
                    "maintenance_interval_km": ("maintainMileage", 1000),
                }
                target, scale = mapping[key]
                body[target] = (
                    value
                    if isinstance(value, str) or key == "crank_length_mm"
                    else round(value * scale)
                )
                if key in {"weight_kg", "wheel_circumference_mm"} and body[target] <= 0:
                    raise ValueError(f"{key} rounds to zero at API precision")
        return body

    def _mutate(
        self, write: Callable[[], None], read: Callable[[], Any], matches: Callable[[Any], bool]
    ) -> dict[str, Any]:
        try:
            write()
        except (IGPSportAPIChangedError, httpx.HTTPError, ValueError) as exc:
            return {
                "status": "uncertain",
                "verified": False,
                "error": str(exc),
                "message": "Write outcome uncertain. Read current state before any retry.",
            }
        try:
            state = read()
            verified = matches(state)
            return {
                "status": "confirmed" if verified else "accepted_unverified",
                "verified": verified,
                "state": state,
            }
        except (IGPSportAPIChangedError, httpx.HTTPError, ValueError) as exc:
            return {"status": "accepted_unverified", "verified": False, "error": str(exc)}

    def create_bike(self, bike: BikeCreate, dry_run: bool = False) -> dict[str, Any]:
        now = datetime.now(UTC)
        body = self._merge(
            {
                "equipmentType": 0,
                "isNoneEquip": False,
                "year": str(now.year),
                "size": "M",
                "sizeId": 6,
                "crankLength": 175,
                "initialMileage": 0,
                "equipmentMileage": 0,
                "periodMileage": 0,
                "maintainMileage": 0,
                "connectedActivitiesNumber": 0,
                "launchedTimestamp": int(now.timestamp() * 1000),
                "isActivated": False,
                "isRetired": False,
            },
            bike,
        )
        if dry_run:
            return {"dry_run": True, "bike": self._preview(body)}
        existing = {b.id for b in self._scan()}

        def read() -> dict[str, Any]:
            candidates = [
                b
                for b in self._scan()
                if b.id not in existing
                and b.launchedTimestamp == body["launchedTimestamp"]
                and b.equipmentBrand == body["equipmentBrand"]
                and b.equipmentName == body["equipmentName"]
                and b.typeName == body["typeName"]
                and b.bikeWeight == body["bikeWeight"]
                and b.wheelSize == body["wheelSize"]
                and b.year == int(body["year"])
                and b.size == body["size"]
                and b.crankLength == body["crankLength"]
            ]
            if len(candidates) != 1:
                raise ValueError("Creation identity ambiguous or missing; do not repeat creation")
            return _public(candidates[0])

        return self._mutate(lambda: self.client.save_equipment(body), read, lambda _: True)

    @staticmethod
    def _preview(body: dict[str, Any]) -> dict[str, Any]:
        return _public(
            Equipment.model_validate(
                {
                    **body,
                    "id": body.get("id", ""),
                    "imageUrl": body.get("imageUrl", ""),
                    "year": int(body["year"]) if body.get("year") else None,
                    "isActivated": int(body["isActivated"]),
                    "isRetired": int(body["isRetired"]),
                }
            )
        )

    def update_bike(
        self, bike_id: str, changes: BikeChanges, dry_run: bool = False
    ) -> dict[str, Any]:
        current = self._find(bike_id)
        body = current.model_dump(exclude_none=True)
        body.update(
            equipmentType=0,
            isNoneEquip=False,
            year=str(current.year) if current.year is not None else "",
            isActivated=bool(current.isActivated),
            isRetired=bool(current.isRetired),
        )
        for key in ("initialMileage", "maintainMileage"):
            body.setdefault(key, 0)
        body = self._merge(body, changes)
        if dry_run:
            return {"dry_run": True, "bike": self._preview(body)}
        expected = self._preview(body)
        keys = {
            "brand",
            "model",
            "bike_type",
            "frame_size",
            "weight_kg",
            "wheel_circumference_mm",
            "crank_length_mm",
            "year",
            "initial_mileage_km",
            "current_odometer_km",
            "maintenance_interval_km",
        }
        return self._mutate(
            lambda: self.client.save_equipment(body),
            lambda: self.get_bike(bike_id),
            lambda b: all(b[k] == expected[k] for k in keys),
        )

    def _bike_mutation(
        self, bike_id: str, write: Callable[[], None], predicate: Callable[[dict[str, Any]], bool]
    ) -> dict[str, Any]:
        def read() -> dict[str, Any]:
            bikes = [_public(b) for b in self._scan()]
            return {
                "bikes": bikes,
                "bike": next((b for b in bikes if b["bike_id"] == bike_id), None),
            }

        return self._mutate(write, read, predicate)

    def set_default_bike(self, bike_id: str) -> dict[str, Any]:
        if self._find(bike_id).isRetired:
            raise ValueError("Default bike must be active")
        return self._bike_mutation(
            bike_id,
            lambda: self.client.activate_equipment(bike_id),
            lambda s: (
                s["bike"] is not None
                and s["bike"]["is_default"]
                and sum(b["is_default"] for b in s["bikes"]) == 1
            ),
        )

    def set_bike_retired(self, bike_id: str, retired: bool) -> dict[str, Any]:
        self._find(bike_id)
        return self._bike_mutation(
            bike_id,
            lambda: self.client.retire_equipment(bike_id, retired),
            lambda s: s["bike"] is not None and s["bike"]["is_retired"] == retired,
        )

    def reset_bike_odometer(self, bike_id: str) -> dict[str, Any]:
        before = self._find(bike_id)
        return self._bike_mutation(
            bike_id,
            lambda: self.client.reset_equipment_odometer(bike_id),
            lambda s: (
                s["bike"] is not None
                and s["bike"]["current_odometer_km"] == 0
                and s["bike"]["total_mileage_km"] == before.equipmentMileage / 1000
                and s["bike"]["initial_mileage_km"] == (before.initialMileage or 0) / 1000
            ),
        )

    def delete_bike(self, bike_id: str, confirm: bool = False) -> dict[str, Any]:
        bike = self._find(bike_id)
        if not confirm:
            return {
                "requires_confirmation": True,
                "bike": _public(bike),
                "requires_retirement": not bool(bike.isRetired),
            }
        if not bike.isRetired:
            raise ValueError("Retire the bike before deletion")
        return self._bike_mutation(
            bike_id, lambda: self.client.delete_equipment(bike_id), lambda s: s["bike"] is None
        )

    def _activity(self, ride_id: int) -> Activity:
        if isinstance(ride_id, bool) or ride_id <= 0:
            raise ValueError("ride_id must be a positive integer")
        return _parse(Activity, self.client.get_activity_equipment_detail(ride_id))

    def get_activity_bike(self, ride_id: int) -> dict[str, Any] | None:
        info = self._activity(ride_id).equipmentInfo
        return (
            {
                "bike_id": info.id,
                "name": info.equipmentName,
                "total_mileage_km": info.equipmentMileage / 1000,
            }
            if info
            else None
        )

    def set_activity_bike(self, ride_id: int, bike_id: str | None) -> dict[str, Any]:
        activity = self._activity(ride_id)
        old = activity.equipmentInfo.id if activity.equipmentInfo else None
        if old == bike_id:
            return {
                "status": "confirmed",
                "verified": True,
                "changed": False,
                "bike": (
                    {
                        "bike_id": old,
                        "name": activity.equipmentInfo.equipmentName,
                        "total_mileage_km": activity.equipmentInfo.equipmentMileage / 1000,
                    }
                    if activity.equipmentInfo
                    else None
                ),
            }
        if bike_id is not None and self._find(bike_id).isRetired:
            raise ValueError("Assignments require an active bike")
        if not activity.startTime or activity.rideDistance is None or activity.rideDistance < 0:
            raise IGPSportAPIChangedError(
                "Activity detail lacks exact startTime or raw rideDistance"
            )
        before = {b.id: b for b in self._scan() if b.id in {old, bike_id}}
        body = {
            "rideId": ride_id,
            "startTime": activity.startTime,
            "rideDistance": activity.rideDistance,
            "id": bike_id or "",
            "oldId": old or "",
        }

        def read() -> dict[str, Any]:
            return {
                "assignment": self.get_activity_bike(ride_id),
                "bikes": [_public(b) for b in self._scan() if b.id in {old, bike_id}],
            }

        def verified(state: dict[str, Any]) -> bool:
            assignment = state["assignment"]
            if (assignment["bike_id"] if assignment else None) != bike_id:
                return False
            after = {b["bike_id"]: b for b in state["bikes"]}
            if set(before) != {v for v in (old, bike_id) if v is not None}:
                return False
            for key, previous in before.items():
                delta = int(key == bike_id) - int(key == old)
                current = after.get(key)
                if current is None or (
                    current["total_mileage_km"]
                    != (previous.equipmentMileage + delta * activity.rideDistance) / 1000
                    or current["connected_activities_count"]
                    != (previous.connectedActivitiesNumber + delta)
                    or current["is_default"] != bool(previous.isActivated)
                ):
                    return False
            return True

        return self._mutate(
            lambda: self.client.set_activity_equipment(body),
            read,
            verified,
        )
