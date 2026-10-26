"""Numerical model oracle tests; no approximation to real hardware is claimed."""

from decimal import Decimal

import pytest

from homemind.simulation.models import Entity, EntityType, Room, initial_state
from homemind.simulation.physics import (
    display_temperature,
    energy_wh,
    rounded,
    step_room,
)
from homemind.simulation.service import SimulationService


def make_entity(kind, config=None, *, entity_id="entity"):
    from homemind.simulation.models import CONFIG_SCHEMAS

    room = Room("room", "测试", Decimal("28"), Decimal("28"))
    entity = Entity(
        entity_id,
        room.id,
        "实体",
        kind,
        CONFIG_SCHEMAS[kind].model_validate(config or {}).model_dump(),
    )
    entity.state = initial_state(entity, room)
    return room, entity


@pytest.mark.parametrize(
    "window,occupied,position,expected",
    [
        (False, False, 100, "28.090"),
        (True, False, 100, "28.410"),
        (False, True, 100, "28.100"),
        (False, False, 0, "28.080"),
    ],
)
def test_minute_passive_heat_equation(window, occupied, position, expected):
    room, opening = make_entity(EntityType.WINDOW, {"initial_open": window})
    _, presence = make_entity(EntityType.OCCUPANCY, {"initial_occupied": occupied})
    _, cover = make_entity(EntityType.COVER, {"initial_position_pct": position})
    step_room(room, [opening, presence, cover])
    assert room.temperature == Decimal(expected)


def test_covers_are_averaged_and_missing_sensors_are_only_internal_assumptions():
    room, first = make_entity(EntityType.COVER, {"initial_position_pct": 0})
    _, second = make_entity(EntityType.COVER, {"initial_position_pct": 100})
    step_room(room, [first, second])
    assert room.temperature == Decimal("28.085")
    room.temperature = Decimal("28")
    step_room(room, [])
    assert room.temperature == Decimal("28.090")


@pytest.mark.parametrize(
    "fan,start,target,expected,power",
    [
        ("auto", "28", 26, "27.870", "850"),
        ("low", "28", 26, "27.940", "550"),
        ("auto", "25", 26, "25.150", "12"),
        ("low", "25", 26, "25.150", "8"),
        ("auto", "26", 26, "26.000", "850"),
    ],
)
def test_cooling_capacity_target_cap_and_standby(fan, start, target, expected, power):
    room, climate = make_entity(EntityType.CLIMATE)
    room.temperature = Decimal(start)
    climate.state.update(mode="cool", fan_mode=fan, target_temperature_c=target)
    step_room(room, [climate])
    assert room.temperature == Decimal(expected)
    assert climate.energy_watt_minutes == Decimal(power)


def test_air_conditioners_act_in_immutable_id_order():
    room, first = make_entity(EntityType.CLIMATE, entity_id="a")
    _, second = make_entity(EntityType.CLIMATE, entity_id="b")
    first.state.update(mode="cool", target_temperature_c=30)
    second.state.update(mode="cool", target_temperature_c=26)
    # At 30.05 C passive heat makes 30.099 C. A cools to 30, then B to 29.78.
    # Reversing the sort makes A idle after B, producing a distinct energy value.
    room.temperature = Decimal("30.05")
    step_room(room, [second, first])
    assert room.temperature == Decimal("29.780")
    assert first.energy_watt_minutes == second.energy_watt_minutes == Decimal(850)


def test_minute_and_display_rounding_are_half_up():
    assert rounded(Decimal("28.0005"), "0.001") == Decimal("28.001")
    assert display_temperature(Decimal("28.05")) == 28.1
    assert energy_wh(Decimal("0.03")) == 0.001
    room, cover = make_entity(EntityType.COVER, {"initial_position_pct": 5})
    step_room(room, [cover])
    assert room.temperature == Decimal("28.081")


def test_snapshot_data_cannot_mutate_live_service():
    service = SimulationService()
    initial = service.snapshot()
    changed = service.snapshot()
    changed["rooms"][0]["name"] = "篡改"
    changed["entities"][0]["config"]["default_brightness_pct"] = 99
    changed["entities"][0]["state"]["power"] = True
    changed["recent_events"].append({"kind": "fake"})
    assert service.snapshot() == initial
