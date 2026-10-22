"""Public human-unit inputs and documented API response models."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Mileage = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Text = Annotated[str, Field(min_length=1, pattern=r"\S")]


class BikeChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand: Text | None = None
    model: Text | None = None
    bike_type: StrictInt | Text | None = None
    weight_kg: Positive | None = None
    wheel_circumference_mm: Positive | None = None
    year: Annotated[int, Field(ge=1, le=9999)] | None = None
    frame_size: StrictInt | Text | None = None
    crank_length_mm: Positive | None = None
    initial_mileage_km: Mileage | None = None
    current_odometer_km: Mileage | None = None
    maintenance_interval_km: Mileage | None = None


class BikeCreate(BikeChanges):
    brand: Text
    model: Text
    bike_type: StrictInt | Text
    weight_kg: Positive
    wheel_circumference_mm: Positive


class Equipment(BaseModel):
    model_config = ConfigDict(strict=True)
    id: StrictStr
    equipmentType: StrictInt
    equipmentBrand: str | None = None
    equipmentName: str | None = None
    typeName: str | None = None
    typeId: int | None = None
    year: int | None = None
    size: str | None = None
    sizeId: int | None = None
    bikeWeight: StrictInt
    wheelSize: StrictInt
    crankLength: float | None = None
    initialMileage: StrictInt | None = None
    equipmentMileage: StrictInt
    periodMileage: StrictInt
    maintainMileage: StrictInt | None = None
    connectedActivitiesNumber: StrictInt
    imageUrl: str
    launchedTimestamp: StrictInt
    isActivated: Annotated[StrictInt, Field(ge=0, le=1)]
    isRetired: Annotated[StrictInt, Field(ge=0, le=1)]


class EquipmentPage(BaseModel):
    model_config = ConfigDict(strict=True)
    total: Annotated[StrictInt, Field(ge=0)]
    items: list[Equipment]


class Lookup(BaseModel):
    model_config = ConfigDict(strict=True)
    id: StrictInt
    name: StrictStr


class Assignment(BaseModel):
    model_config = ConfigDict(strict=True)
    id: StrictStr
    equipmentName: StrictStr
    equipmentMileage: StrictInt


class Activity(BaseModel):
    model_config = ConfigDict(strict=True)
    equipmentInfo: Assignment | None = None
    startTime: str | None = None
    rideDistance: StrictInt | None = None
