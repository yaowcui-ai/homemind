"""Independent public snapshots that never expose hidden physical temperatures."""

from copy import deepcopy
from decimal import Decimal

from homemind.simulation.models import Entity, EntityType, FaultMode, Room
from homemind.simulation.physics import display_temperature, energy_wh


def observable(entity: Entity) -> bool:
    return (
        not entity.archived
        and entity.enabled
        and entity.available
        and entity.known
        and entity.fault_mode != FaultMode.OFFLINE
    )


def entity_view(entity: Entity) -> dict:
    state = deepcopy(entity.state)
    if observable(entity):
        if entity.type == EntityType.TEMPERATURE:
            state["temperature_c"] = display_temperature(Decimal(str(state["temperature_c"])))
    else:
        state = {key: None for key in state}
    return {
        "id": entity.id,
        "room_id": entity.room_id,
        "name": entity.name,
        "type": entity.type.value,
        "enabled": entity.enabled,
        "available": entity.available and entity.fault_mode != FaultMode.OFFLINE,
        "known": entity.known,
        "state": state,
        "config": deepcopy(entity.config),
        "version": entity.version,
        "observed_at_minutes": entity.observed_at_minutes,
        "energy_wh": energy_wh(entity.energy_watt_minutes),
        "fault": {"mode": entity.fault_mode.value, "delay_minutes": entity.delay_minutes},
        "pending_until_minutes": entity.pending.due if entity.pending else None,
    }


def room_view(room: Room, entities: dict[str, Entity]) -> dict:
    def primary_reading(entity_id: str | None, field: str):
        primary = entities.get(entity_id)
        if primary is None or not observable(primary):
            return None
        return entity_view(primary)["state"][field]

    windows = [
        entity
        for entity in entities.values()
        if entity.room_id == room.id
        and entity.type == EntityType.WINDOW
        and entity.enabled
        and not entity.archived
    ]
    if any(observable(entity) and entity.state["window_open"] for entity in windows):
        window_open = True
    elif windows and all(observable(entity) for entity in windows):
        window_open = False
    else:
        window_open = None
    return {
        "id": room.id,
        "name": room.name,
        "primary_temperature_entity_id": room.primary_temperature_entity_id,
        "primary_occupancy_entity_id": room.primary_occupancy_entity_id,
        "temperature_c": primary_reading(room.primary_temperature_entity_id, "temperature_c"),
        "occupied": primary_reading(room.primary_occupancy_entity_id, "occupied"),
        "window_open": window_open,
    }
