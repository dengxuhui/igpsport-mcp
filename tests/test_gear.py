"""Gear tests use only local models, fake state and HTTP transports."""

import asyncio
import copy
import json
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError

from igpsport_mcp.client import endpoints as ep
from igpsport_mcp.client.auth import Token
from igpsport_mcp.client.igpsport import IGPSportClient
from igpsport_mcp.client.region import get_profile
from igpsport_mcp.config import load_config
from igpsport_mcp.exceptions import IGPSportAPIChangedError
from igpsport_mcp.gear.models import BikeChanges, BikeCreate
from igpsport_mcp.gear.service import GearService
from igpsport_mcp.server import build_server
from igpsport_mcp.tools._service import IGPSportService


def equipment(bike_id="a", **changes):
    return (
        dict(
            id=bike_id,
            equipmentType=0,
            equipmentBrand="Brand",
            equipmentName="Model",
            typeName="RoadBike",
            typeId=1,
            year=2024,
            size="M",
            sizeId=6,
            bikeWeight=10000,
            wheelSize=2096,
            crankLength=172.5,
            initialMileage=1000,
            equipmentMileage=5000,
            periodMileage=2000,
            maintainMileage=500000,
            connectedActivitiesNumber=1,
            imageUrl="https://example.test/image",
            launchedTimestamp=1700000000123,
            isActivated=0,
            isRetired=0,
        )
        | changes
    )


class FakeGear:
    def __init__(self):
        self.bikes = [equipment(), equipment("b", isRetired=1)]
        self.writes = []
        self.detail = {
            "startTime": "2026-10-20 17:19:08",
            "rideDistance": 3000,
            "equipmentInfo": {"id": "a", "equipmentName": "Brand Model", "equipmentMileage": 5000},
        }

    def list_equipment(self, retired, page, page_size):
        bikes = [b for b in self.bikes if bool(b["isRetired"]) == retired]
        return {
            "total": len(bikes),
            "items": copy.deepcopy(bikes[(page - 1) * page_size : page * page_size]),
        }

    def get_equipment_types(self):
        return [{"id": 1, "name": "RoadBike"}]

    def get_equipment_sizes(self):
        return [{"id": 6, "name": "M"}]

    def save_equipment(self, body):
        self.writes.append(copy.deepcopy(body))
        value = dict(
            body,
            id=body.get("id", "new"),
            year=int(body["year"]),
            isActivated=int(body["isActivated"]),
            isRetired=int(body["isRetired"]),
        )
        value.setdefault("imageUrl", "default")
        previous = next((b for b in self.bikes if b["id"] == value["id"]), None)
        if previous:
            value["equipmentMileage"] += value["initialMileage"] - previous["initialMileage"]
        self.bikes = [b for b in self.bikes if b["id"] != value["id"]] + [value]

    def activate_equipment(self, bike_id):
        self.writes.append("activate")
        for b in self.bikes:
            b["isActivated"] = int(b["id"] == bike_id)

    def retire_equipment(self, bike_id, retired):
        self.writes.append("retire")
        was_default = any(b["id"] == bike_id and b["isActivated"] for b in self.bikes)
        for b in self.bikes:
            if b["id"] == bike_id:
                b["isRetired"] = int(retired)
                b["isActivated"] = 0
        remaining = [b for b in self.bikes if not b["isRetired"]]
        if was_default and retired and remaining:
            remaining[0]["isActivated"] = 1

    def reset_equipment_odometer(self, bike_id):
        self.writes.append("reset")
        next(b for b in self.bikes if b["id"] == bike_id)["periodMileage"] = 0

    def delete_equipment(self, bike_id):
        self.writes.append("delete")
        self.bikes = [b for b in self.bikes if b["id"] != bike_id]

    def get_activity_equipment_detail(self, ride_id):
        return copy.deepcopy(self.detail)

    def set_activity_equipment(self, body):
        self.writes.append(body)
        for b in self.bikes:
            factor = int(b["id"] == body["id"]) - int(b["id"] == body["oldId"])
            b["equipmentMileage"] += factor * body["rideDistance"]
            b["connectedActivitiesNumber"] += factor
        self.detail.pop("equipmentInfo", None)
        if body["id"]:
            b = next(b for b in self.bikes if b["id"] == body["id"])
            self.detail["equipmentInfo"] = {
                "id": b["id"],
                "equipmentName": "Brand Model",
                "equipmentMileage": b["equipmentMileage"],
            }


@pytest.fixture
def gear():
    return GearService(FakeGear())


def creation(**changes):
    return BikeCreate.model_validate(
        dict(brand="Brand", model="New", bike_type=1, weight_kg=10.123, wheel_circumference_mm=2096)
        | changes
    )


def test_creation_defaults_units_and_identification(gear):
    preview = gear.create_bike(creation(), True)
    assert preview["bike"]["year"] == datetime.now(UTC).year
    assert preview["bike"]["frame_size"] == "M"
    assert preview["bike"]["crank_length_mm"] == 175
    assert not gear.client.writes
    result = gear.create_bike(creation(initial_mileage_km=1.234, bike_type="DH"))
    assert result["status"] == "confirmed"
    assert result["state"]["bike_id"] == "new"
    body = gear.client.writes[-1]
    assert body["bikeWeight"] == 10123
    assert body["initialMileage"] == 1234
    assert body["equipmentMileage"] == body["connectedActivitiesNumber"] == 0
    assert body["isNoneEquip"] is False
    assert "id" not in body
    assert "image" not in str(result).lower()


@pytest.mark.parametrize(
    "changes",
    [
        dict(weight_kg=0),
        dict(weight_kg=float("inf")),
        dict(initial_mileage_km=-1),
        dict(crank_length_mm=0),
        dict(brand=" "),
        dict(wheel_circumference_mm=float("nan")),
        dict(imageUrl="x"),
    ],
)
def test_invalid_inputs(changes):
    with pytest.raises(ValidationError):
        creation(**changes)


def test_required_creation_inputs():
    with pytest.raises(ValidationError):
        BikeCreate.model_validate({})


def test_custom_choices_and_null_rejection(gear):
    with pytest.raises(ValueError):
        gear.create_bike(creation(bike_type="a" * 15), True)
    with pytest.raises(ValueError):
        gear.create_bike(creation(bike_type=999), True)
    assert gear.create_bike(creation(frame_size="Custom"), True)["bike"]["frame_size_id"] == 999
    with pytest.raises(ValueError):
        gear.update_bike("a", BikeChanges(brand=None))


def test_update_preserves_complete_body_and_images(gear):
    before = copy.deepcopy(gear.client.bikes[0])
    assert gear.update_bike("a", BikeChanges(model="Changed", maintenance_interval_km=0))[
        "verified"
    ]
    body = gear.client.writes[-1]
    for key, value in before.items():
        if key not in {"equipmentName", "maintainMileage", "year", "isActivated", "isRetired"}:
            assert body[key] == value
    assert body["year"] == "2024"
    assert body["maintainMileage"] == 0
    assert body["isActivated"] is False
    assert body["isNoneEquip"] is False
    assert gear.update_bike("a", BikeChanges(weight_kg=8), True)["dry_run"]
    assert len(gear.client.writes) == 1


def test_list_get_and_repeated_pagination(gear):
    assert gear.list_bikes()["total"] == 1
    assert gear.list_bikes("all", 1)["has_more"]
    assert gear.get_bike("b")["is_retired"]
    calls = []

    def pages(retired, page, page_size):
        calls.append(page)
        return {"total": 3, "items": [equipment(str(page))] if page <= 3 else []}

    gear.client.list_equipment = pages
    assert gear.list_bikes()["total"] == 3
    assert calls == [1, 2, 3]
    gear.client.list_equipment = lambda *a: {"total": 4, "items": [equipment()]}
    with pytest.raises(IGPSportAPIChangedError, match="repeated"):
        gear.list_bikes()
    gear.client.list_equipment = lambda *a: {"total": 4, "items": []}
    assert gear.list_bikes()["total"] == 0


def test_flags_reset_and_delete(gear):
    with pytest.raises(ValueError, match="active"):
        gear.set_default_bike("b")
    assert gear.set_default_bike("a")["state"]["bike"]["is_default"]
    assert gear.reset_bike_odometer("a")["verified"]
    assert gear.delete_bike("a")["requires_confirmation"]
    with pytest.raises(ValueError, match="Retire"):
        gear.delete_bike("a", True)
    assert gear.set_bike_retired("a", True)["verified"]
    assert gear.set_bike_retired("a", False)["verified"]
    assert not gear.get_bike("a")["is_default"]
    assert gear.delete_bike("b", True)["verified"]


def test_assign_reassign_unassign_and_mileage(gear):
    assert gear.set_activity_bike(1, "a")["changed"] is False
    assert not gear.client.writes
    gear.set_bike_retired("b", False)
    assert gear.set_activity_bike(1, "b")["verified"]
    assert gear.get_bike("a")["total_mileage_km"] == 2
    assert gear.get_bike("b")["total_mileage_km"] == 8
    assert gear.get_bike("b")["connected_activities_count"] == 2
    assert gear.client.writes[-1] == {
        "rideId": 1,
        "startTime": "2026-10-20 17:19:08",
        "rideDistance": 3000,
        "oldId": "a",
        "id": "b",
    }
    assert gear.set_activity_bike(1, None)["verified"]
    assert gear.get_activity_bike(1) is None
    assert gear.get_bike("b")["total_mileage_km"] == 5
    assert gear.set_activity_bike(1, "a")["verified"]
    assert gear.get_bike("a")["current_odometer_km"] == 2


def test_assignment_requires_raw_fields(gear):
    gear.client.detail.pop("startTime")
    with pytest.raises(IGPSportAPIChangedError):
        gear.set_activity_bike(1, None)
    assert not gear.client.writes


def test_mutation_uncertainty_and_readback_failure(gear):
    def fail(*args):
        raise IGPSportAPIChangedError("network failed")

    gear.client.save_equipment = fail
    assert gear.update_bike("a", BikeChanges(model="Changed"))["status"] == "uncertain"
    gear.client.reset_equipment_odometer = lambda *args: None
    assert gear.reset_bike_odometer("a")["status"] == "accepted_unverified"
    gear.client.save_equipment = lambda *args: None
    result = gear.create_bike(creation())
    assert result["status"] == "accepted_unverified"
    assert "ambiguous" in result["error"]


def test_ambiguous_creation_never_guesses(gear):
    original = gear.client.save_equipment

    def duplicate(body):
        original(body)
        gear.client.bikes.append(dict(gear.client.bikes[-1], id="another"))

    gear.client.save_equipment = duplicate
    result = gear.create_bike(creation())
    assert result["status"] == "accepted_unverified"
    assert "state" not in result
    assert len(gear.client.writes) == 1


class RecordingSigner:
    def __init__(self):
        self.calls = []

    def generate_signature(self, method, path, timestamp, nonce, body):
        self.calls.append((method, path, timestamp, nonce, body))
        return f"recorded-{len(self.calls)}"


def make_client(tmp_path, handler, region="intl"):
    config = load_config({"IGPSPORT_REGION": region, "IGPSPORT_CACHE_DIR": str(tmp_path)})
    client = IGPSportClient(
        config,
        http=httpx.Client(
            base_url=get_profile(region).api_base, transport=httpx.MockTransport(handler)
        ),
        signer=RecordingSigner(),
    )
    client._token = Token(
        access_token="shared",
        refresh_token="r",
        expires_at=9999999999,
        region=region,
        member_id="1",
    )
    return client


@pytest.mark.parametrize("region", ["cn", "intl"])
def test_all_routes_auth_and_write_bodies(tmp_path, region):
    seen = []

    def handler(request):
        assert request.headers["authorization"] == "Bearer shared"
        assert str(request.url).startswith(get_profile(region).api_base + "/")
        seen.append(request)
        if request.method == "POST":
            assert request.headers["content-type"] == "application/json"
            assert isinstance(json.loads(request.content), dict)
        return httpx.Response(200, json={"code": 0, "data": True})

    with make_client(tmp_path, handler, region) as client:
        client.list_equipment(False, 2)
        client.get_equipment_types()
        client.get_equipment_sizes()
        client.get_activity_equipment_detail(123)
        client.save_equipment({"id": "a", "equipmentName": "自行车"})
        client.activate_equipment("a")
        client.retire_equipment("a", True)
        client.reset_equipment_odometer("a")
        client.delete_equipment("a")
        client.set_activity_equipment({"rideId": 123})
        signer = client._signers[client._profile.access_key]
    if region == "cn":
        assert len(signer.calls) == len(seen)
        for request, (method, path, timestamp, nonce, body) in zip(seen, signer.calls, strict=True):
            assert method == request.method
            assert path == request.url.raw_path.decode("ascii")
            assert body == request.content.decode("utf-8")
            assert timestamp == request.headers["x-timestamp"]
            assert nonce == request.headers["x-nonce"]
            assert request.headers["x-signature"].startswith("recorded-")
            assert request.headers["x-access-key"] == "AKIDWebClient"
    else:
        assert signer.calls == []
        for request in seen:
            assert (
                not {"x-signature", "x-nonce", "x-timestamp", "x-access-key"}
                & request.headers.keys()
            )
    assert [r.url.path for r in seen] == [
        ep.PATH_GEAR_LIST,
        ep.PATH_GEAR_TYPES,
        ep.PATH_GEAR_SIZES,
        ep.PATH_GEAR_ACTIVITY_DETAIL,
        ep.PATH_GEAR_SAVE,
        ep.PATH_GEAR_ACTIVATE,
        ep.PATH_GEAR_RETIRE,
        ep.PATH_GEAR_RESET,
        ep.PATH_GEAR_DELETE,
        ep.PATH_GEAR_RELATION,
    ]
    assert str(seen[0].url.query, "ascii") == "IsRetired=0&PageIndex=2&pageSize=20"
    assert seen[3].url.query == b"activityId=123"
    assert [r.method for r in seen] == ["GET"] * 4 + ["POST"] * 6
    assert [json.loads(r.content) for r in seen[4:]] == [
        {"id": "a", "equipmentName": "自行车"},
        {"id": "a", "isActivated": 1},
        {"id": "a", "isRetired": 1},
        {"id": "a"},
        {"id": "a"},
        {"rideId": 123},
    ]
    assert ep.PATH_ACTIVITY_DETAIL.split("?")[0] != ep.PATH_GEAR_ACTIVITY_DETAIL


@pytest.mark.parametrize("region", ["cn", "intl"])
def test_retry_defaults_and_non_replayed_gear_writes(tmp_path, monkeypatch, region):
    monkeypatch.setattr("igpsport_mcp.client.igpsport.time.sleep", lambda _: None)
    attempts = []

    def handler(request):
        attempts.append(request)
        raise httpx.ReadError("response lost", request=request)

    with make_client(tmp_path, handler, region) as client:
        for write in [
            lambda: client.save_equipment({}),
            lambda: client.activate_equipment("a"),
            lambda: client.retire_equipment("a", True),
            lambda: client.reset_equipment_odometer("a"),
            lambda: client.delete_equipment("a"),
            lambda: client.set_activity_equipment({"rideId": 123}),
        ]:
            with pytest.raises(IGPSportAPIChangedError, match="after 1 attempts"):
                write()
            assert len(attempts) == 1
            attempts.clear()
        for read in [
            lambda: client.list_equipment(False),
            client.get_equipment_types,
            client.get_equipment_sizes,
            lambda: client.get_activity_equipment_detail(123),
        ]:
            with pytest.raises(IGPSportAPIChangedError, match="after 3 attempts"):
                read()
            assert len(attempts) == 3
            attempts.clear()
        with pytest.raises(IGPSportAPIChangedError):
            client.get_user_interval_info()
        assert len(attempts) == 3


@pytest.mark.parametrize(
    "status,payload",
    [(500, {"code": 0}), (200, {"code": 7}), (200, {}), (200, {"code": 0, "data": False})],
)
def test_response_errors(tmp_path, status, payload):
    with (
        make_client(tmp_path, lambda _: httpx.Response(status, json=payload)) as client,
        pytest.raises((httpx.HTTPError, IGPSportAPIChangedError)),
    ):
        client.save_equipment({})


def test_response_model_drift_and_extra_fields(gear):
    gear.client.bikes[0]["futureField"] = "ignored"
    assert "futureField" not in gear.get_bike("a")
    gear.client.bikes[0].pop("wheelSize")
    with pytest.raises(IGPSportAPIChangedError):
        gear.list_bikes()


@pytest.mark.parametrize("region", ["cn", "intl"])
def test_regional_gear_service_live_reads(tmp_path, region):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"code": 0, "data": {"total": 1, "items": [equipment()]}})

    with make_client(tmp_path, handler, region) as client:
        service = IGPSportService(client._config, client=client)
        assert service.gear.list_bikes()["bikes"][0]["bike_id"] == "a"
        assert service.gear.list_bikes()["total"] == 1
        assert len(requests) == 2
        assert service._db is None


@pytest.mark.parametrize("region", ["cn", "intl"])
def test_gear_accessor_is_credential_free(tmp_path, monkeypatch, region):
    def forbidden(*args, **kwargs):
        pytest.fail("startup accessed credentials, signing or network")

    monkeypatch.setattr(IGPSportClient, "_request_raw", forbidden)
    monkeypatch.setattr(IGPSportClient, "_get_signer", forbidden)
    monkeypatch.setattr("igpsport_mcp.config.Config.require_credentials", forbidden)
    cfg = load_config({"IGPSPORT_REGION": region, "IGPSPORT_CACHE_DIR": str(tmp_path)})
    service = IGPSportService(cfg)
    assert service._client is None
    assert service._gear is None
    try:
        assert service.gear is service.gear
        assert service.gear.client is service.client
        assert service.client._profile.key == region
        assert service.client._signers == {}
        assert service._db is None
    finally:
        service.client.close()


@pytest.mark.parametrize("region", ["cn", "intl"])
def test_lazy_startup_registration_and_typed_schemas(tmp_path, monkeypatch, region):
    def forbidden(*args, **kwargs):
        pytest.fail("server startup created a client")

    monkeypatch.setattr(IGPSportClient, "__init__", forbidden)
    cfg = load_config({"IGPSPORT_REGION": region, "IGPSPORT_CACHE_DIR": str(tmp_path)})
    service = IGPSportService(cfg, client=FakeGear())
    assert service._gear is None
    assert service.gear.client is service.client
    assert service._db is None
    server = build_server(cfg)
    tools = asyncio.run(server.list_tools())
    assert len(tools) == 28
    by_name = {t.name: t for t in tools}
    schema = by_name["create_bike"].inputSchema
    assert schema["$defs"]["BikeCreate"]["required"] == [
        "brand",
        "model",
        "bike_type",
        "weight_kg",
        "wheel_circumference_mm",
    ]
    assert schema["$defs"]["BikeCreate"]["additionalProperties"] is False
    assert by_name["delete_bike"].inputSchema["properties"]["confirm"]["default"] is False
    assert (
        by_name["set_activity_bike"].inputSchema["properties"]["bike_id"]["anyOf"][1]["type"]
        == "null"
    )
    assert not (tmp_path / "activities.db").exists()


def test_initial_mileage_recalculation_and_retirement_side_effects(gear):
    result = gear.update_bike("a", BikeChanges(initial_mileage_km=3))
    assert result["verified"]
    assert result["state"]["total_mileage_km"] == 7
    gear.set_bike_retired("b", False)
    gear.set_default_bike("a")
    result = gear.set_bike_retired("a", True)
    assert result["verified"]
    bikes = {b["bike_id"]: b for b in result["state"]["bikes"]}
    assert not bikes["a"]["is_default"]
    assert bikes["b"]["is_default"]


def test_accepted_write_with_failed_verification(gear):
    def accepted_then_unreadable(bike_id):
        gear.client.writes.append("reset")
        gear.client.list_equipment = lambda *args: {"items": "changed shape"}

    gear.client.reset_equipment_odometer = accepted_then_unreadable
    result = gear.reset_bike_odometer("a")
    assert result["status"] == "accepted_unverified"
    assert gear.client.writes == ["reset"]


def test_assignment_incorrect_mileage_is_not_confirmed(gear):
    original = gear.client.set_activity_equipment

    def assign_without_removing_old_mileage(body):
        original(body)
        gear.client.bikes[0]["equipmentMileage"] += body["rideDistance"]

    gear.client.set_activity_equipment = assign_without_removing_old_mileage
    assert gear.set_activity_bike(1, None)["status"] == "accepted_unverified"
