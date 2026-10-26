"""Transparent demo assumptions; Decimal minutes, never wall-clock integration.

Quality is about observation, not physical existence. Active physical sensors keep
their signals when readings are unknown/offline. Missing signals assume closed
windows and no occupancy internally; public observations still remain unknown.
All enabled occupancy signals contribute via any(True), independently of the
explicit primary used for the public room observation.
"""

from decimal import ROUND_HALF_UP, Decimal

from homemind.simulation.models import Entity, EntityType, Room

MODEL_VERSION = "m2-decimal-minute-v1"
OUTDOOR_TEMPERATURE = Decimal("32")


def rounded(value: Decimal, precision: str) -> Decimal:
    return value.quantize(Decimal(precision), rounding=ROUND_HALF_UP)


def display_temperature(value: Decimal) -> float:
    return float(rounded(value, "0.1"))


def energy_wh(watt_minutes: Decimal) -> float:
    return float(rounded(watt_minutes / Decimal(60), "0.001"))


def update_hvac_action(entity: Entity, room: Room) -> None:
    if entity.state["mode"] == "off":
        entity.state["hvac_action"] = "off"
    elif room.temperature > Decimal(str(entity.state["target_temperature_c"])):
        entity.state["hvac_action"] = "cooling"
    else:
        entity.state["hvac_action"] = "idle"


def step_room(room: Room, entities: list[Entity]) -> None:
    active = [entity for entity in entities if entity.enabled and not entity.archived]
    window_open = any(
        entity.state["window_open"] for entity in active if entity.type == EntityType.WINDOW
    )
    occupied = any(
        entity.state["occupied"] for entity in active if entity.type == EntityType.OCCUPANCY
    )
    positions = [
        Decimal(str(entity.state["position_pct"]))
        for entity in active
        if entity.type == EntityType.COVER
    ]
    mean_position = sum(positions) / len(positions) if positions else Decimal(100)
    coefficient = Decimal("0.10") if window_open else Decimal("0.02")
    room.temperature += (
        (OUTDOOR_TEMPERATURE - room.temperature) * coefficient
        + mean_position / Decimal(100) * Decimal("0.01")
        + (Decimal("0.01") if occupied else Decimal(0))
    )
    # Immutable IDs define the action order when multiple air conditioners exist.
    for entity in sorted(active, key=lambda item: item.id):
        if entity.type == EntityType.CLIMATE:
            update_hvac_action(entity, room)
            if entity.state["mode"] == "off":
                power = 0
            else:
                auto = entity.state["fan_mode"] == "auto"
                if entity.state["hvac_action"] == "cooling":
                    target = Decimal(str(entity.state["target_temperature_c"]))
                    rate = Decimal("0.22") if auto else Decimal("0.15")
                    room.temperature = max(target, room.temperature - rate)
                    power = 850 if auto else 550
                else:
                    power = 12 if auto else 8
            entity.energy_watt_minutes += Decimal(power)
        elif entity.type == EntityType.LIGHT:
            if entity.state["power"]:
                power = 2 + rounded(
                    Decimal(10) * Decimal(str(entity.state["brightness_pct"])) / Decimal(100), "1"
                )
                entity.energy_watt_minutes += power
    room.temperature = rounded(room.temperature, "0.001")
