"""Strict input schemas and private mutable domain records."""

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    model_validator,
)


class EntityType(StrEnum):
    LIGHT = "light"
    CLIMATE = "climate"
    COVER = "cover"
    TEMPERATURE = "temperature"
    OCCUPANCY = "occupancy"
    WINDOW = "window"


class FaultMode(StrEnum):
    NONE = "none"
    OFFLINE = "offline"
    FAIL_BEFORE = "fail_before"
    RESPONSE_LOST = "response_lost"
    NO_EFFECT = "no_effect"
    DELAYED = "delayed"


Name = Annotated[str, Field(strict=True, min_length=1, max_length=80)]
Identifier = Annotated[str, Field(strict=True, min_length=1)]
Temperature = Annotated[StrictFloat, Field(ge=0, le=50, allow_inf_nan=False)]
Brightness = Annotated[StrictInt, Field(ge=0, le=100)]
DefaultBrightness = Annotated[StrictInt, Field(ge=1, le=100)]
TargetTemperature = Annotated[StrictInt, Field(ge=16, le=30)]
Minutes = Annotated[StrictInt, Field(ge=1, le=1440)]
Scalar = str | int | float | bool | None


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    nullable_fields: ClassVar[frozenset[str]] = frozenset()
    require_fields: ClassVar[bool] = False

    @model_validator(mode="after")
    def validate_supplied_fields(self):
        if self.require_fields and not self.model_fields_set:
            raise ValueError("至少指定一个字段")
        for name in self.model_fields_set - self.nullable_fields:
            if getattr(self, name) is None:
                raise ValueError(f"{name} 不允许为空")
        return self


class RoomCreate(InputModel):
    name: Name
    initial_temperature_c: Temperature = 27.0


class RoomPatch(InputModel):
    require_fields = True
    nullable_fields = frozenset({"primary_temperature_entity_id", "primary_occupancy_entity_id"})
    name: Name | None = None
    primary_temperature_entity_id: Identifier | None = None
    primary_occupancy_entity_id: Identifier | None = None


class EntityCreate(InputModel):
    room_id: Identifier
    name: Name
    type: EntityType
    config: dict[str, Any] = Field(default_factory=dict)


class EntityPatch(InputModel):
    require_fields = True
    name: Name | None = None
    room_id: Identifier | None = None
    enabled: StrictBool | None = None
    config: dict[str, Any] | None = None


class LightConfig(InputModel):
    default_brightness_pct: DefaultBrightness = 60


class ClimateConfig(InputModel):
    initial_target_temperature_c: TargetTemperature = 26


class CoverConfig(InputModel):
    initial_position_pct: Brightness = 100


class SensorConfig(InputModel):
    pass


class OccupancyConfig(InputModel):
    initial_occupied: StrictBool = False


class WindowConfig(InputModel):
    initial_open: StrictBool = False


CONFIG_SCHEMAS = {
    EntityType.LIGHT: LightConfig,
    EntityType.CLIMATE: ClimateConfig,
    EntityType.COVER: CoverConfig,
    EntityType.TEMPERATURE: SensorConfig,
    EntityType.OCCUPANCY: OccupancyConfig,
    EntityType.WINDOW: WindowConfig,
}


class LightControl(InputModel):
    require_fields = True
    power: StrictBool | None = None
    brightness_pct: Brightness | None = None

    @model_validator(mode="after")
    def no_contradictory_light_state(self):
        if self.power is False and self.brightness_pct is not None and self.brightness_pct > 0:
            raise ValueError("关灯不能同时指定正亮度")
        return self


class ClimateControl(InputModel):
    require_fields = True
    mode: Literal["off", "cool"] | None = None
    target_temperature_c: TargetTemperature | None = None
    fan_mode: Literal["low", "auto"] | None = None


class CoverControl(InputModel):
    position_pct: Brightness


CONTROL_SCHEMAS = {
    EntityType.LIGHT: ("set_light", LightControl),
    EntityType.CLIMATE: ("set_climate", ClimateControl),
    EntityType.COVER: ("set_cover", CoverControl),
}


class ControlRequest(InputModel):
    action: Identifier
    parameters: dict[str, Any]
    expected_world_id: Identifier | None = None


class EventRequest(InputModel):
    entity_id: Identifier
    temperature_c: Temperature | None = None
    occupied: StrictBool | None = None
    window_open: StrictBool | None = None
    available: StrictBool | None = None
    known: StrictBool | None = None

    @model_validator(mode="after")
    def at_least_one_change(self):
        if self.model_fields_set == {"entity_id"}:
            raise ValueError("至少指定一个模拟事件字段")
        return self


class FaultRequest(InputModel):
    mode: FaultMode
    delay_minutes: Minutes = 2


class AdvanceRequest(InputModel):
    minutes: Minutes


class ResetRequest(InputModel):
    pass


class SimulationError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class Room:
    id: str
    name: str
    initial_temperature: Decimal
    temperature: Decimal
    primary_temperature_entity_id: str | None = None
    primary_occupancy_entity_id: str | None = None


@dataclass
class PendingControl:
    due: int
    parameters: dict[str, Any]


@dataclass
class Entity:
    id: str
    room_id: str
    name: str
    type: EntityType
    config: dict[str, Any]
    state: dict[str, Scalar] = field(default_factory=dict)
    enabled: bool = True
    available: bool = True
    known: bool = True
    archived: bool = False
    version: int = 1
    observed_at_minutes: int = 0
    energy_watt_minutes: Decimal = Decimal(0)
    fault_mode: FaultMode = FaultMode.NONE
    delay_minutes: int = 2
    pending: PendingControl | None = None


def initial_state(entity: Entity, room: Room) -> dict[str, Scalar]:
    """Build fresh state from the saved per-type preferences, never shared dicts."""
    match entity.type:
        case EntityType.LIGHT:
            return {"power": False, "brightness_pct": 0}
        case EntityType.CLIMATE:
            return {
                "mode": "off",
                "target_temperature_c": entity.config["initial_target_temperature_c"],
                "fan_mode": "auto",
                "hvac_action": "off",
            }
        case EntityType.COVER:
            return {"position_pct": entity.config["initial_position_pct"]}
        case EntityType.TEMPERATURE:
            return {"temperature_c": float(room.temperature)}
        case EntityType.OCCUPANCY:
            return {"occupied": entity.config["initial_occupied"]}
        case EntityType.WINDOW:
            return {"window_open": entity.config["initial_open"]}
