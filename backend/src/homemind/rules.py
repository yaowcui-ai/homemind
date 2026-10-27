"""Pure rule planning and constraint validation, independent of persistence."""

from typing import Literal

from pydantic import Field, model_validator

from homemind.simulation.models import (
    ControlRequest,
    EntityType,
    Identifier,
    InputModel,
    Minutes,
    SimulationError,
    TargetTemperature,
)


class RuleRequest(InputModel):
    scenario: Literal["homecoming", "sleep", "away"]
    room_ids: list[Identifier] = Field(min_length=1, max_length=100)
    target_temperature_c: TargetTemperature | None = None
    ready_in_minutes: Minutes | None = None
    keep_entity_ids: list[Identifier] = Field(default_factory=list, max_length=1000)
    protected_room_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    expected_world_id: Identifier | None = None

    @model_validator(mode="after")
    def meaningful_fields(self):
        self.room_ids = sorted(set(self.room_ids))
        self.keep_entity_ids = sorted(set(self.keep_entity_ids))
        self.protected_room_ids = sorted(set(self.protected_room_ids))
        if self.scenario != "away" and len(self.room_ids) != 1:
            raise ValueError("回家和睡眠需要恰好一个房间")
        if self.scenario == "away" and "target_temperature_c" in self.model_fields_set:
            raise ValueError("离家不接受温度")
        if self.scenario != "homecoming" and "ready_in_minutes" in self.model_fields_set:
            raise ValueError("仅回家接受提前量")
        return self


def normalize(request: RuleRequest, preferences: dict) -> dict:
    result = request.model_dump(exclude_none=True)
    if request.scenario != "away" and request.target_temperature_c is None:
        result["target_temperature_c"] = preferences[
            "comfort_temperature_c" if request.scenario == "homecoming" else "sleep_temperature_c"
        ]
    if request.scenario == "homecoming" and request.ready_in_minutes is None:
        result["ready_in_minutes"] = preferences["arrival_lead_minutes"]
    return result


def validate_references(engine, request):
    for room_id in set(request["room_ids"] + request["protected_room_ids"]):
        engine._room(room_id)
    for entity_id in request["keep_entity_ids"]:
        entity = engine._entity(entity_id)
        if not entity.enabled:
            raise SimulationError(422, "disabled_reference", "保留实体必须已启用")
    if set(request["room_ids"]) & set(request["protected_room_ids"]):
        raise SimulationError(422, "protected_conflict", "目标房间同时受保护，请明确调整范围")
    if request.get("expected_world_id", engine._world_id) != engine._world_id:
        raise SimulationError(409, "world_changed", "仿真环境已重置，请刷新后重新操作")


def plan_rules(engine, request, preferences):
    validate_references(engine, request)
    snapshot = engine.snapshot()
    room_views = {room["id"]: room for room in snapshot["rooms"]}
    actions, constraints, temperatures = [], [], []
    for room_id in request["room_ids"]:
        room = engine._room(room_id)
        view = room_views[room_id]
        entities = [
            e
            for e in engine._entities.values()
            if e.room_id == room_id and not e.archived and e.enabled
        ]
        for kind in (EntityType.LIGHT, EntityType.COVER, EntityType.CLIMATE):
            if not any(e.type == kind for e in entities):
                constraints.append(
                    {
                        "label": f"{room.name} / {kind.value}",
                        "outcome": "failed",
                        "message": "缺少已启用的所需设备",
                    }
                )
        can_cool = True
        if request["scenario"] != "away":
            temperatures.append(
                {
                    "room_id": room_id,
                    "room_name": room.name,
                    "target": request["target_temperature_c"],
                }
            )
            if view["window_open"] is not False:
                can_cool = False
                constraints.append(
                    {
                        "label": f"{room.name} / 窗户",
                        "outcome": "failed" if view["window_open"] else "unknown",
                        "message": "窗户打开或状态未知，需要手动确认；未启动制冷",
                    }
                )
        for entity in entities:
            if entity.id in request["keep_entity_ids"]:
                continue
            if entity.type == EntityType.LIGHT:
                action = "set_light"
                parameters = (
                    {"power": True, "brightness_pct": entity.config["default_brightness_pct"]}
                    if request["scenario"] == "homecoming"
                    else {"power": False}
                )
            elif entity.type == EntityType.COVER:
                action, parameters = "set_cover", {"position_pct": 0}
            elif entity.type == EntityType.CLIMATE:
                if request["scenario"] != "away" and not can_cool:
                    continue
                action = "set_climate"
                parameters = (
                    {"mode": "off"}
                    if request["scenario"] == "away"
                    else {
                        "mode": "cool",
                        "target_temperature_c": request["target_temperature_c"],
                        "fan_mode": preferences["fan_mode"],
                    }
                )
            else:
                continue
            control = ControlRequest(
                action=action, parameters=parameters, expected_world_id=engine._world_id
            )
            engine._validate_control(entity, control)
            actions.append(
                {
                    "entity_id": entity.id,
                    "entity_name": entity.name,
                    "room_name": room.name,
                    "action": action,
                    "parameters": parameters,
                }
            )
    return {
        "actions": actions,
        "constraints": constraints,
        "temperatures": temperatures,
        "due_at_minutes": (
            engine._minutes + request["ready_in_minutes"]
            if request["scenario"] == "homecoming"
            else None
        ),
    }
