"""One locked in-memory world. All validation precedes mutation inside the lock."""

from collections import deque
from copy import deepcopy
from decimal import Decimal
from threading import RLock
from uuid import uuid4

from pydantic import ValidationError

from homemind.simulation.defaults import default_home, new_id
from homemind.simulation.models import (
    CONFIG_SCHEMAS,
    CONTROL_SCHEMAS,
    ControlRequest,
    Entity,
    EntityCreate,
    EntityPatch,
    EntityType,
    EventRequest,
    FaultMode,
    FaultRequest,
    PendingControl,
    Room,
    RoomCreate,
    RoomPatch,
    SimulationError,
    initial_state,
)
from homemind.simulation.physics import (
    MODEL_VERSION,
    OUTDOOR_TEMPERATURE,
    energy_wh,
    rounded,
    step_room,
    update_hvac_action,
)
from homemind.simulation.views import entity_view, observable, room_view


class SimulationService:
    def __init__(self, home_id: str = "demo-home", *, seed: bool = True):
        self._lock = RLock()
        self._home_id = home_id
        self._rooms, self._entities = default_home() if seed else ({}, {})
        self._world_id = uuid4().hex
        self._revision = 0
        self._config_revision = 0
        self._minutes = 0
        self._event_sequence = 0
        self._events = deque(maxlen=50)
        self._new_events = []
        self._archives = []

    def _room(self, room_id: str) -> Room:
        room = self._rooms.get(room_id)
        if room is None:
            raise SimulationError(404, "not_found", "找不到房间")
        return room

    def _entity(self, entity_id: str) -> Entity:
        entity = self._entities.get(entity_id)
        if entity is None or entity.archived:
            raise SimulationError(404, "not_found", "找不到实体，或该实体已归档")
        return entity

    def _record(self, kind: str, message: str, entity_id: str | None = None) -> None:
        self._event_sequence += 1
        self._events.append(
            {
                "sequence": self._event_sequence,
                "at_minutes": self._minutes,
                "kind": kind,
                "message": message,
                "entity_id": entity_id,
            }
        )
        self._new_events.append(deepcopy(self._events[-1]))

    def _changed(self, kind: str, message: str, entity_id=None, *, config=False) -> dict:
        self._revision += 1
        if config:
            self._config_revision += 1
        self._record(kind, message, entity_id)
        return self._snapshot()

    def _snapshot(self) -> dict:
        return {
            "home_id": self._home_id,
            "world_id": self._world_id,
            "revision": self._revision,
            "config_revision": self._config_revision,
            "simulated_minutes": self._minutes,
            "model_version": MODEL_VERSION,
            "outdoor_temperature_c": float(OUTDOOR_TEMPERATURE),
            "energy_wh": energy_wh(
                sum((entity.energy_watt_minutes for entity in self._entities.values()), Decimal(0))
            ),
            "rooms": [room_view(room, self._entities) for room in self._rooms.values()],
            "entities": [
                entity_view(entity) for entity in self._entities.values() if not entity.archived
            ],
            "archived_count": sum(entity.archived for entity in self._entities.values()),
            "recent_events": deepcopy(list(self._events)),
        }

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot()

    def _touch(self, entity: Entity) -> None:
        entity.version += 1
        if observable(entity):
            entity.observed_at_minutes = self._minutes

    def _cancel_pending(self, entity: Entity) -> None:
        if entity.pending is not None:
            entity.pending = None
            self._record("pending_cancelled", f"已取消 {entity.name} 的延迟动作", entity.id)

    def _clear_bindings(self, entity: Entity) -> None:
        for room in self._rooms.values():
            if room.primary_temperature_entity_id == entity.id:
                room.primary_temperature_entity_id = None
            if room.primary_occupancy_entity_id == entity.id:
                room.primary_occupancy_entity_id = None

    def create_room(self, request: RoomCreate) -> dict:
        with self._lock:
            temperature = rounded(Decimal(str(request.initial_temperature_c)), "0.001")
            room = Room(new_id("room"), request.name, temperature, temperature)
            self._rooms[room.id] = room
            return self._changed("room_created", f"已创建房间 {room.name}", config=True)

    def patch_room(self, room_id: str, request: RoomPatch) -> dict:
        with self._lock:
            room = self._room(room_id)
            for field, kind in [
                ("primary_temperature_entity_id", EntityType.TEMPERATURE),
                ("primary_occupancy_entity_id", EntityType.OCCUPANCY),
            ]:
                value = getattr(request, field)
                if field in request.model_fields_set and value is not None:
                    primary = self._entity(value)
                    if primary.room_id != room_id or primary.type != kind or not primary.enabled:
                        raise SimulationError(
                            422, "invalid_primary", "主读数须选择本房间已启用的对应传感器"
                        )
            for field in request.model_fields_set:
                setattr(room, field, getattr(request, field))
            return self._changed("room_updated", f"已更新房间 {room.name}", config=True)

    def delete_room(self, room_id: str) -> dict:
        with self._lock:
            room = self._room(room_id)
            if any(
                entity.room_id == room_id and not entity.archived
                for entity in self._entities.values()
            ):
                raise SimulationError(409, "room_not_empty", "请先迁移或归档房间中的实体")
            del self._rooms[room_id]
            return self._changed("room_deleted", f"已删除房间 {room.name}", config=True)

    @staticmethod
    def _validate_config(kind: EntityType, config: dict) -> dict:
        try:
            return CONFIG_SCHEMAS[kind].model_validate(config).model_dump()
        except ValidationError as error:
            raise SimulationError(
                422, "invalid_config", "配置不符合该实体类型的能力或参数范围"
            ) from error

    def create_entity(self, request: EntityCreate) -> dict:
        with self._lock:
            room = self._room(request.room_id)
            config = self._validate_config(request.type, request.config)
            entity = Entity(new_id(request.type.value), room.id, request.name, request.type, config)
            entity.state = initial_state(entity, room)
            entity.observed_at_minutes = self._minutes
            self._entities[entity.id] = entity
            return self._changed(
                "entity_created", f"已创建实体 {entity.name}", entity.id, config=True
            )

    def patch_entity(self, entity_id: str, request: EntityPatch) -> dict:
        with self._lock:
            entity = self._entity(entity_id)
            target_room = self._room(request.room_id) if request.room_id is not None else None
            config = None
            if "config" in request.model_fields_set:
                config = self._validate_config(entity.type, {**entity.config, **request.config})
            moving = target_room is not None and target_room.id != entity.room_id
            disabling = request.enabled is False and entity.enabled
            if moving or disabling or config is not None:
                self._cancel_pending(entity)
            if moving or disabling:
                self._clear_bindings(entity)
            if target_room is not None:
                entity.room_id = target_room.id
            if request.name is not None:
                entity.name = request.name
            if request.enabled is not None:
                entity.enabled = request.enabled
            if config is not None:
                entity.config = config
            if moving and entity.type == EntityType.TEMPERATURE:
                entity.state["temperature_c"] = float(target_room.temperature)
            if entity.type == EntityType.CLIMATE:
                update_hvac_action(entity, self._rooms[entity.room_id])
            self._touch(entity)
            return self._changed(
                "entity_updated", f"已更新实体 {entity.name}", entity.id, config=True
            )

    def delete_entity(self, entity_id: str) -> dict:
        with self._lock:
            entity = self._entity(entity_id)
            self._archives.append(
                {
                    "at_minutes": self._minutes,
                    "world_id": self._world_id,
                    "entity": deepcopy(entity),
                }
            )
            self._cancel_pending(entity)
            self._clear_bindings(entity)
            entity.archived = True
            entity.enabled = False
            self._touch(entity)
            return self._changed(
                "entity_archived", f"已归档实体 {entity.name}", entity.id, config=True
            )

    def _validate_control(self, entity: Entity, request: ControlRequest) -> dict:
        schema = CONTROL_SCHEMAS.get(entity.type)
        if schema is None or request.action != schema[0]:
            raise SimulationError(422, "unsupported_action", "该实体不支持此控制动作")
        try:
            return schema[1].model_validate(request.parameters).model_dump(exclude_unset=True)
        except ValidationError as error:
            raise SimulationError(
                422, "invalid_parameters", "控制参数不符合能力或范围要求"
            ) from error

    def _apply_control(self, entity: Entity, parameters: dict) -> None:
        before = dict(entity.state)
        if entity.type == EntityType.LIGHT:
            if "brightness_pct" in parameters:
                brightness = parameters["brightness_pct"]
                entity.state.update(power=brightness > 0, brightness_pct=brightness)
            elif parameters["power"]:
                entity.state.update(
                    power=True, brightness_pct=entity.config["default_brightness_pct"]
                )
            else:
                entity.state.update(power=False, brightness_pct=0)
        elif entity.type == EntityType.CLIMATE:
            entity.state.update(parameters)
            update_hvac_action(entity, self._rooms[entity.room_id])
        elif entity.type == EntityType.COVER:
            if entity.state["position_pct"] != parameters["position_pct"]:
                entity.energy_watt_minutes += Decimal("3")  # 0.05 Wh per actual movement.
            entity.state.update(parameters)
        if entity.state != before:
            self._touch(entity)

    def control(self, entity_id: str, request: ControlRequest) -> dict:
        with self._lock:
            entity = self._entity(entity_id)
            if (
                request.expected_world_id is not None
                and request.expected_world_id != self._world_id
            ):
                raise SimulationError(409, "world_changed", "仿真环境已重置，请刷新后重新操作")
            parameters = self._validate_control(entity, request)
            if entity.pending is not None:
                raise SimulationError(
                    409, "pending_conflict", "该实体已有待执行动作，请推进时间或取消故障"
                )
            if not entity.enabled or not entity.available or entity.fault_mode == FaultMode.OFFLINE:
                outcome, message = "failed", "实体已停用或无法连接，动作未执行"
            elif entity.fault_mode == FaultMode.FAIL_BEFORE:
                outcome, message = "failed", "模拟动作前失败，动作未执行"
            elif entity.fault_mode == FaultMode.NO_EFFECT:
                outcome, message = "failed", "模拟设备无效果，读回未核验动作成功"
            elif entity.fault_mode == FaultMode.DELAYED:
                entity.pending = PendingControl(
                    self._minutes + entity.delay_minutes, dict(parameters)
                )
                self._touch(entity)
                outcome, message = "unknown", "动作已排队，推进仿真时间后可独立读回核验"
            else:
                self._apply_control(entity, parameters)
                if entity.fault_mode == FaultMode.RESPONSE_LOST:
                    outcome, message = "unknown", "模拟响应丢失，请独立读取状态核验"
                elif not entity.known:
                    outcome, message = "unknown", "已执行但读数未知，请恢复读数后核验"
                else:
                    outcome, message = "verified", "动作已执行并读回核验"
            self._changed("control_" + outcome, f"{entity.name}：{message}", entity.id)
            return {
                "outcome": outcome,
                "message": message,
                "entity_id": entity.id,
                "world_id": self._world_id,
                "revision": self._revision,
            }

    def _refresh_room_readings(self, room_id: str) -> None:
        room = self._rooms[room_id]
        for entity in self._entities.values():
            if entity.room_id == room_id and not entity.archived:
                if entity.type == EntityType.TEMPERATURE:
                    entity.state["temperature_c"] = float(room.temperature)
                    self._touch(entity)
                elif entity.type == EntityType.CLIMATE:
                    update_hvac_action(entity, room)
                    self._touch(entity)

    def event(self, request: EventRequest) -> dict:
        with self._lock:
            entity = self._entity(request.entity_id)
            fields = request.model_dump(exclude_unset=True, exclude={"entity_id"})
            allowed_signal = {
                EntityType.TEMPERATURE: "temperature_c",
                EntityType.OCCUPANCY: "occupied",
                EntityType.WINDOW: "window_open",
            }.get(entity.type)
            if any(field not in {"available", "known", allowed_signal} for field in fields):
                raise SimulationError(
                    422, "invalid_event", "事件只能更新该类型的传感信号及观测质量"
                )
            for field in ("available", "known"):
                if field in fields:
                    setattr(entity, field, fields[field])
            if "temperature_c" in fields:
                room = self._rooms[entity.room_id]
                room.temperature = rounded(Decimal(str(fields["temperature_c"])), "0.001")
                self._refresh_room_readings(room.id)
            elif allowed_signal in fields:
                entity.state[allowed_signal] = fields[allowed_signal]
            self._touch(entity)
            return self._changed(
                "simulation_event", f"已模拟 {entity.name} 的环境或质量变化", entity.id
            )

    def set_fault(self, entity_id: str, request: FaultRequest) -> dict:
        with self._lock:
            entity = self._entity(entity_id)
            self._cancel_pending(entity)
            entity.fault_mode = request.mode
            entity.delay_minutes = request.delay_minutes
            self._touch(entity)
            return self._changed(
                "fault_changed", f"{entity.name} 故障模式：{request.mode.value}", entity.id
            )

    def advance(self, minutes: int) -> dict:
        with self._lock:
            for _ in range(minutes):
                # Commands due at minute N take effect at its boundary, before N's model step.
                self._minutes += 1
                for entity in sorted(self._entities.values(), key=lambda item: item.id):
                    if entity.pending is not None and entity.pending.due <= self._minutes:
                        pending = entity.pending
                        entity.pending = None
                        self._apply_control(entity, pending.parameters)
                        self._record(
                            "delayed_applied", f"{entity.name} 的延迟动作已生效", entity.id
                        )
                for room in self._rooms.values():
                    step_room(
                        room,
                        [entity for entity in self._entities.values() if entity.room_id == room.id],
                    )
                    self._refresh_room_readings(room.id)
            return self._changed("time_advanced", f"已推进 {minutes} 个仿真分钟")

    def reset(self) -> dict:
        with self._lock:
            for entity in self._entities.values():
                self._cancel_pending(entity)
            for room in self._rooms.values():
                room.temperature = room.initial_temperature
            self._world_id = uuid4().hex
            self._minutes = 0
            for entity in self._entities.values():
                entity.energy_watt_minutes = Decimal(0)
                if entity.archived:
                    continue
                entity.state = initial_state(entity, self._rooms[entity.room_id])
                entity.available = entity.known = True
                entity.fault_mode = FaultMode.NONE
                entity.delay_minutes = 2
                entity.observed_at_minutes = 0
                self._touch(entity)
            return self._changed("world_reset", "已保留当前配置并重置运行状态，旧环境动作已失效")
