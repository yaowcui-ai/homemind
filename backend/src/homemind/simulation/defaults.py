"""Versioned two-room template with fresh immutable identities on each copy."""

from decimal import Decimal
from uuid import uuid4

from homemind.simulation.models import CONFIG_SCHEMAS, Entity, EntityType, Room, initial_state


def new_id(kind: str) -> str:
    return f"{kind}-{uuid4().hex}"


def default_home() -> tuple[dict[str, Room], dict[str, Entity]]:
    rooms = {}
    entities = {}
    for name, temperature, brightness, target in [("客厅", "28", 60, 26), ("卧室", "27", 30, 27)]:
        room = Room(new_id("room"), name, Decimal(temperature), Decimal(temperature))
        rooms[room.id] = room
        for kind, suffix, config in [
            (EntityType.LIGHT, "主灯", {"default_brightness_pct": brightness}),
            (EntityType.CLIMATE, "空调", {"initial_target_temperature_c": target}),
            (EntityType.COVER, "电动窗帘", {}),
            (EntityType.TEMPERATURE, "温度传感器", {}),
            (EntityType.OCCUPANCY, "有人传感器", {}),
            (EntityType.WINDOW, "窗户传感器", {}),
        ]:
            entity = Entity(
                new_id(kind.value),
                room.id,
                name + suffix,
                kind,
                CONFIG_SCHEMAS[kind].model_validate(config).model_dump(),
            )
            entity.state = initial_state(entity, room)
            entities[entity.id] = entity
            if kind == EntityType.TEMPERATURE:
                room.primary_temperature_entity_id = entity.id
            elif kind == EntityType.OCCUPANCY:
                room.primary_occupancy_entity_id = entity.id
    return rooms, entities
