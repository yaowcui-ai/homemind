"""M2 contract and state-machine tests against the real in-process API."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from homemind.app import create_app
from homemind.config import Settings


@pytest.fixture
def client():
    with TestClient(create_app(Settings(environment="test"))) as instance:
        yield instance


def snapshot(client):
    response = client.get("/simulation")
    assert response.status_code == 200, response.text
    return response.json()


def entity(state, kind, room_id=None):
    return next(
        item
        for item in state["entities"]
        if item["type"] == kind and (room_id is None or item["room_id"] == room_id)
    )


def by_id(state, entity_id):
    return next(item for item in state["entities"] if item["id"] == entity_id)


def control(client, target, action, parameters, **extra):
    return client.post(
        f"/simulation/controls/{target['id']}",
        json={"action": action, "parameters": parameters, **extra},
    )


def event(client, target, **fields):
    return client.post("/simulation/events", json={"entity_id": target["id"], **fields})


def fault(client, target, mode, **fields):
    return client.post(f"/simulation/faults/{target['id']}", json={"mode": mode, **fields})


def advance(client, minutes):
    response = client.post("/simulation/advance", json={"minutes": minutes})
    assert response.status_code == 200, response.text
    return response.json()


def test_default_template_and_independent_apps(client):
    before = snapshot(client)
    assert before["home_id"] == "demo-home"
    assert before["simulated_minutes"] == before["energy_wh"] == 0
    assert before["outdoor_temperature_c"] == 32
    assert len(before["rooms"]) == 2
    assert len(before["entities"]) == 12
    assert before["archived_count"] == 0
    assert len({item["id"] for item in before["entities"]}) == 12
    assert len({item["id"] for item in before["rooms"]}) == 2
    assert [room["temperature_c"] for room in before["rooms"]] == [28, 27]
    for room in before["rooms"]:
        assert room["occupied"] is False and room["window_open"] is False
        assert by_id(before, room["primary_temperature_entity_id"])["type"] == "temperature"
        assert by_id(before, room["primary_occupancy_entity_id"])["type"] == "occupancy"
        assert {item["type"] for item in before["entities"] if item["room_id"] == room["id"]} == {
            "light",
            "climate",
            "cover",
            "temperature",
            "occupancy",
            "window",
        }
    assert entity(before, "light")["state"] == {"power": False, "brightness_pct": 0}
    assert entity(before, "climate")["state"] == {
        "mode": "off",
        "target_temperature_c": 26,
        "fan_mode": "auto",
        "hvac_action": "off",
    }
    assert all(
        item["enabled"] and item["available"] and item["known"] for item in before["entities"]
    )
    assert snapshot(client) == before
    with TestClient(create_app(Settings(environment="test"))) as other:
        separate = snapshot(other)
        assert separate["world_id"] != before["world_id"]
        assert {item["id"] for item in before["entities"]}.isdisjoint(
            item["id"] for item in separate["entities"]
        )


def test_controls_are_partial_and_verify_actual_state(client):
    before = snapshot(client)
    light = entity(before, "light")
    result = control(
        client, light, "set_light", {"power": True}, expected_world_id=before["world_id"]
    )
    assert result.status_code == 200
    assert result.json()["outcome"] == "verified"
    assert result.json()["entity_id"] == light["id"]
    assert result.json()["world_id"] == before["world_id"]
    assert by_id(snapshot(client), light["id"])["state"] == {"power": True, "brightness_pct": 60}
    control(client, light, "set_light", {"brightness_pct": 0})
    assert by_id(snapshot(client), light["id"])["state"]["power"] is False
    climate = entity(before, "climate")
    control(client, climate, "set_climate", {"target_temperature_c": 24})
    assert by_id(snapshot(client), climate["id"])["state"] == {
        "mode": "off",
        "target_temperature_c": 24,
        "fan_mode": "auto",
        "hvac_action": "off",
    }
    control(client, climate, "set_climate", {"mode": "cool", "fan_mode": "low"})
    assert by_id(snapshot(client), climate["id"])["state"]["target_temperature_c"] == 24
    cover = entity(before, "cover")
    control(client, cover, "set_cover", {"position_pct": 25})
    control(client, cover, "set_cover", {"position_pct": 25})
    assert by_id(snapshot(client), cover["id"])["energy_wh"] == 0.05
    assert entity(snapshot(client), "window")["state"]["window_open"] is False


@pytest.mark.parametrize(
    ("kind", "action", "parameters"),
    [
        ("temperature", "set_light", {"power": True}),
        ("light", "set_climate", {"mode": "cool"}),
        ("light", "set_light", {}),
        ("light", "set_light", {"power": False, "brightness_pct": 10}),
        ("light", "set_light", {"brightness_pct": True}),
        ("light", "set_light", {"brightness_pct": 1.5}),
        ("light", "set_light", {"brightness_pct": "60"}),
        ("light", "set_light", {"brightness_pct": 101}),
        ("light", "set_light", {"power": 1}),
        ("light", "set_light", {"color": "red"}),
        ("climate", "set_climate", {"mode": "heat"}),
        ("climate", "set_climate", {"target_temperature_c": 15}),
        ("climate", "set_climate", {"target_temperature_c": 26.5}),
        ("climate", "set_climate", {"target_temperature_c": False}),
        ("climate", "set_climate", {"fan_mode": "high"}),
        ("cover", "set_cover", {"position_pct": -1}),
        ("cover", "set_cover", {"position_pct": 101}),
        ("cover", "set_cover", {"position_pct": False}),
    ],
)
def test_invalid_controls_are_atomic(client, kind, action, parameters):
    before = snapshot(client)
    response = control(client, entity(before, kind), action, parameters)
    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"]["code"], str)
    assert snapshot(client) == before


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "true", '"28"', "51", "-1"])
def test_invalid_environment_numbers_never_mutate(client, value):
    before = snapshot(client)
    sensor = entity(before, "temperature")
    response = client.post(
        "/simulation/events",
        content='{"entity_id":"' + sensor["id"] + '","temperature_c":' + value + "}",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert snapshot(client) == before


def test_events_validate_all_fields_before_mutation(client):
    before = snapshot(client)
    light = entity(before, "light")
    response = event(client, light, available=False, occupied=True)
    assert response.status_code == 422
    assert snapshot(client) == before
    sensor = entity(before, "temperature")
    response = event(client, sensor, temperature_c=29.26)
    assert response.status_code == 200
    assert response.json()["rooms"][0]["temperature_c"] == 29.3
    assert event(client, sensor, occupied=True).status_code == 422
    assert event(client, sensor).status_code == 422


def test_room_entity_crud_bindings_and_archive(client):
    initial = snapshot(client)
    response = client.post("/simulation/rooms", json={"name": "书房", "initial_temperature_c": 25})
    assert response.status_code == 200
    new_room = response.json()["rooms"][-1]
    assert new_room["temperature_c"] is None
    assert new_room["occupied"] is None and new_room["window_open"] is None
    response = client.post(
        "/simulation/entities",
        json={
            "room_id": new_room["id"],
            "name": "书桌灯",
            "type": "light",
            "config": {"default_brightness_pct": 75},
        },
    )
    assert response.status_code == 200
    light = response.json()["entities"][-1]
    assert light["config"] == {"default_brightness_pct": 75}
    assert client.delete(f"/simulation/rooms/{new_room['id']}").status_code == 409
    original_room = initial["rooms"][0]
    response = client.patch(
        f"/simulation/entities/{light['id']}",
        json={
            "room_id": original_room["id"],
            "name": "阅读灯",
            "config": {"default_brightness_pct": 80},
        },
    )
    assert response.status_code == 200
    assert by_id(response.json(), light["id"])["name"] == "阅读灯"
    assert client.delete(f"/simulation/rooms/{new_room['id']}").status_code == 200
    primary = entity(initial, "temperature", original_room["id"])
    client.patch(
        f"/simulation/entities/{primary['id']}", json={"room_id": initial["rooms"][1]["id"]}
    )
    state = snapshot(client)
    assert state["rooms"][0]["primary_temperature_entity_id"] is None
    assert state["rooms"][0]["temperature_c"] is None
    assert state["rooms"][1]["primary_temperature_entity_id"] != primary["id"]
    assert client.delete(f"/simulation/entities/{light['id']}").status_code == 200
    after = snapshot(client)
    assert after["archived_count"] == 1
    assert all(item["id"] != light["id"] for item in after["entities"])
    assert control(client, light, "set_light", {"power": True}).status_code == 404
    assert after["config_revision"] > initial["config_revision"]


def test_primary_binding_is_explicit_and_validated(client):
    initial = snapshot(client)
    room = initial["rooms"][0]
    response = client.post(
        "/simulation/entities",
        json={
            "room_id": room["id"],
            "type": "temperature",
            "name": "备用温度",
        },
    )
    second = response.json()["entities"][-1]
    assert response.json()["rooms"][0]["primary_temperature_entity_id"] != second["id"]
    response = client.patch(
        f"/simulation/rooms/{room['id']}",
        json={
            "name": "起居室",
            "primary_temperature_entity_id": second["id"],
        },
    )
    assert response.status_code == 200
    assert response.json()["rooms"][0]["temperature_c"] == 28
    before = snapshot(client)
    response = client.patch(
        f"/simulation/rooms/{room['id']}",
        json={
            "name": "不应保存",
            "primary_temperature_entity_id": entity(initial, "light")["id"],
        },
    )
    assert response.status_code == 422
    assert snapshot(client) == before
    client.patch(f"/simulation/entities/{second['id']}", json={"enabled": False})
    assert snapshot(client)["rooms"][0]["primary_temperature_entity_id"] is None
    client.patch(f"/simulation/entities/{second['id']}", json={"enabled": True})
    assert snapshot(client)["rooms"][0]["temperature_c"] is None


@pytest.mark.parametrize(
    "kind,config",
    [
        ("light", {"capability": "heat"}),
        ("light", {"default_brightness_pct": 0}),
        ("light", {"default_brightness_pct": True}),
        ("climate", {"initial_target_temperature_c": 31}),
        ("climate", {"initial_target_temperature_c": 26.2}),
        ("cover", {"initial_position_pct": 101}),
        ("temperature", {"initial_temperature_c": 30}),
        ("occupancy", {"initial_occupied": 1}),
        ("window", {"initial_open": "false"}),
    ],
)
def test_config_whitelists_reject_unknown_and_coerced_values(client, kind, config):
    before = snapshot(client)
    response = client.post(
        "/simulation/entities",
        json={
            "room_id": before["rooms"][0]["id"],
            "name": "非法",
            "type": kind,
            "config": config,
        },
    )
    assert response.status_code == 422
    target = entity(before, kind)
    response = client.patch(
        f"/simulation/entities/{target['id']}", json={"name": "非法", "config": config}
    )
    assert response.status_code == 422
    assert snapshot(client) == before


def test_quality_masks_states_and_room_aggregates(client):
    before = snapshot(client)
    temperature = entity(before, "temperature")
    event(client, temperature, known=False)
    assert by_id(snapshot(client), temperature["id"])["state"] == {"temperature_c": None}
    assert snapshot(client)["rooms"][0]["temperature_c"] is None
    event(client, temperature, known=True, available=False)
    assert snapshot(client)["rooms"][0]["temperature_c"] is None
    advance(client, 1)
    event(client, temperature, available=True)
    assert snapshot(client)["rooms"][0]["temperature_c"] == 28.1
    occupancy = entity(before, "occupancy")
    event(client, occupancy, occupied=True, known=False)
    assert snapshot(client)["rooms"][0]["occupied"] is None
    light = entity(before, "light")
    client.patch(f"/simulation/entities/{light['id']}", json={"enabled": False})
    assert all(value is None for value in by_id(snapshot(client), light["id"])["state"].values())
    assert control(client, light, "set_light", {"power": True}).json()["outcome"] == "failed"


def test_window_aggregation_keeps_unknown_and_open_precedence(client):
    initial = snapshot(client)
    room = initial["rooms"][0]
    first = entity(initial, "window")
    response = client.post(
        "/simulation/entities",
        json={
            "room_id": room["id"],
            "name": "第二扇窗",
            "type": "window",
        },
    )
    second = response.json()["entities"][-1]
    event(client, first, known=False)
    assert snapshot(client)["rooms"][0]["window_open"] is None
    event(client, second, window_open=True)
    assert snapshot(client)["rooms"][0]["window_open"] is True
    event(client, second, window_open=False)
    client.patch(f"/simulation/entities/{first['id']}", json={"enabled": False})
    assert snapshot(client)["rooms"][0]["window_open"] is False
    client.delete(f"/simulation/entities/{second['id']}")
    assert snapshot(client)["rooms"][0]["window_open"] is None


@pytest.mark.parametrize(
    "mode,outcome,applied",
    [
        ("none", "verified", True),
        ("offline", "failed", False),
        ("fail_before", "failed", False),
        ("response_lost", "unknown", True),
        ("no_effect", "failed", False),
        ("delayed", "unknown", False),
    ],
)
def test_fault_modes_are_persistent_with_truthful_results(client, mode, outcome, applied):
    light = entity(snapshot(client), "light")
    assert fault(client, light, mode).status_code == 200
    response = control(client, light, "set_light", {"power": True})
    assert response.status_code == 200
    assert response.json()["outcome"] == outcome
    after = by_id(snapshot(client), light["id"])
    assert after["fault"]["mode"] == mode
    if mode == "offline":
        assert after["available"] is False
        assert after["state"]["power"] is None
        fault(client, light, "none")
        assert by_id(snapshot(client), light["id"])["state"]["power"] is False
    else:
        assert after["state"]["power"] is applied


def test_delayed_action_uses_simulated_time_and_rejects_conflict(client):
    light = entity(snapshot(client), "light")
    fault(client, light, "delayed", delay_minutes=2)
    assert (
        control(client, light, "set_light", {"brightness_pct": 80}).json()["outcome"] == "unknown"
    )
    assert by_id(snapshot(client), light["id"])["pending_until_minutes"] == 2
    before = snapshot(client)
    assert control(client, light, "set_light", {"power": False}).status_code == 409
    assert snapshot(client) == before
    assert by_id(advance(client, 1), light["id"])["state"]["power"] is False
    due = by_id(advance(client, 1), light["id"])
    assert due["state"]["brightness_pct"] == 80
    assert due["pending_until_minutes"] is None
    assert due["fault"]["mode"] == "delayed"


@pytest.mark.parametrize("change", ["archive", "disable", "move", "config", "fault", "reset"])
def test_configuration_changes_cancel_pending_actions(client, change):
    before = snapshot(client)
    light = entity(before, "light")
    fault(client, light, "delayed")
    control(client, light, "set_light", {"power": True})
    if change == "archive":
        client.delete(f"/simulation/entities/{light['id']}")
    elif change == "fault":
        fault(client, light, "none")
    elif change == "reset":
        client.post("/simulation/reset", json={})
    else:
        fields = {
            "disable": {"enabled": False},
            "move": {"room_id": before["rooms"][1]["id"]},
            "config": {"config": {"default_brightness_pct": 90}},
        }
        client.patch(f"/simulation/entities/{light['id']}", json=fields[change])
    after = advance(client, 3)
    assert any(item["kind"] == "pending_cancelled" for item in after["recent_events"])
    if change != "archive":
        result = by_id(after, light["id"])
        assert result["pending_until_minutes"] is None
        assert result["state"]["power"] in (False, None)


def test_reset_preserves_config_and_ids_but_refuses_old_world(client):
    initial = snapshot(client)
    light = entity(initial, "light")
    cover = entity(initial, "cover")
    client.patch(
        f"/simulation/entities/{light['id']}",
        json={
            "name": "新的名称",
            "room_id": initial["rooms"][1]["id"],
            "enabled": False,
            "config": {"default_brightness_pct": 42},
        },
    )
    client.delete(f"/simulation/entities/{cover['id']}")
    climate = entity(initial, "climate")
    fault(client, climate, "response_lost")
    control(client, climate, "set_climate", {"mode": "cool"})
    event(client, entity(initial, "temperature"), temperature_c=35, known=False)
    advance(client, 20)
    configured = snapshot(client)
    response = client.post("/simulation/reset", json={})
    assert response.status_code == 200
    reset = response.json()
    assert reset["world_id"] != initial["world_id"]
    assert reset["simulated_minutes"] == reset["energy_wh"] == 0
    assert reset["config_revision"] == configured["config_revision"]
    assert reset["rooms"] == [
        {**room, "temperature_c": 28 if index == 0 else 27}
        for index, room in enumerate(initial["rooms"])
    ]
    saved = by_id(reset, light["id"])
    assert saved["name"] == "新的名称" and saved["enabled"] is False
    assert saved["room_id"] == initial["rooms"][1]["id"]
    assert saved["config"]["default_brightness_pct"] == 42
    assert reset["archived_count"] == 1 and len(reset["entities"]) == 11
    assert by_id(reset, climate["id"])["fault"]["mode"] == "none"
    assert by_id(reset, climate["id"])["state"]["mode"] == "off"
    response = control(
        client, climate, "set_climate", {"mode": "cool"}, expected_world_id=initial["world_id"]
    )
    assert response.status_code == 409
    assert snapshot(client) == reset


def test_deterministic_minutes_energy_and_unknown_physical_signals(client):
    initial = snapshot(client)
    light = entity(initial, "light")
    climate = entity(initial, "climate")
    control(client, light, "set_light", {"brightness_pct": 65})
    control(client, climate, "set_climate", {"mode": "cool", "target_temperature_c": 16})
    once = advance(client, 20)
    assert by_id(once, light["id"])["energy_wh"] == 3  # 2 + ROUND_HALF_UP(6.5) = 9 W
    assert by_id(once, climate["id"])["energy_wh"] == 283.333
    assert once["rooms"][0]["temperature_c"] < 28
    client.post("/simulation/reset", json={})
    control(client, light, "set_light", {"brightness_pct": 65})
    control(client, climate, "set_climate", {"mode": "cool", "target_temperature_c": 16})
    advance(client, 10)
    twice = advance(client, 10)
    assert once["rooms"] == twice["rooms"]
    assert once["energy_wh"] == twice["energy_wh"]
    assert [item["state"] for item in once["entities"]] == [
        item["state"] for item in twice["entities"]
    ]
    client.post("/simulation/reset", json={})
    window = entity(initial, "window")
    event(client, window, window_open=True, known=False)
    after = advance(client, 1)
    assert after["rooms"][0]["window_open"] is None
    assert after["rooms"][0]["temperature_c"] == 28.4


def test_recent_events_bounded_and_reads_are_stable(client):
    light = entity(snapshot(client), "light")
    for index in range(70):
        control(client, light, "set_light", {"power": bool(index % 2)})
    after = snapshot(client)
    assert len(after["recent_events"]) == 50
    sequence = [item["sequence"] for item in after["recent_events"]]
    assert sequence == sorted(set(sequence))
    assert snapshot(client) == after


def test_concurrent_mutations_do_not_lose_revisions(client):
    before = snapshot(client)
    room_id = before["rooms"][0]["id"]

    def create(index):
        return client.post(
            "/simulation/entities",
            json={
                "room_id": room_id,
                "type": "light",
                "name": f"灯{index}",
            },
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(create, range(24)))
    assert all(response.status_code == 200 for response in responses)
    after = snapshot(client)
    assert len(after["entities"]) == 36
    assert len({item["id"] for item in after["entities"]}) == 36
    assert after["revision"] == before["revision"] + 24
    assert after["config_revision"] == before["config_revision"] + 24


@pytest.mark.parametrize("minutes", [0, 1441, 1.5, True, "5"])
def test_advance_bounds_and_strict_integer(client, minutes):
    before = snapshot(client)
    assert client.post("/simulation/advance", json={"minutes": minutes}).status_code == 422
    assert snapshot(client) == before


def test_production_does_not_mount_unauthenticated_simulation():
    with TestClient(create_app(Settings(environment="production"))) as client:
        assert client.get("/simulation").status_code == 404
        assert client.post("/simulation/reset", json={}).status_code == 404
        assert all(
            not path.startswith("/simulation")
            for path in client.get("/openapi.json").json()["paths"]
        )


def test_unknown_ids_return_structured_404(client):
    response = client.patch("/simulation/entities/missing", json={"name": "无"})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


def test_offline_observation_does_not_stop_running_cooling(client):
    initial = snapshot(client)
    climate = entity(initial, "climate")
    control(client, climate, "set_climate", {"mode": "cool", "target_temperature_c": 16})
    fault(client, climate, "offline")
    state = advance(client, 1)
    assert state["rooms"][0]["temperature_c"] == 27.9
    assert by_id(state, climate["id"])["state"]["mode"] is None
    assert by_id(state, climate["id"])["energy_wh"] == 14.167
    fault(client, climate, "none")
    assert by_id(snapshot(client), climate["id"])["state"]["mode"] == "cool"


def test_missing_primary_has_no_implicit_fallback_and_thermal_state_survives(client):
    initial = snapshot(client)
    room = initial["rooms"][0]
    sensor = entity(initial, "temperature")
    client.delete(f"/simulation/entities/{sensor['id']}")
    advance(client, 20)
    response = client.post(
        "/simulation/entities",
        json={
            "room_id": room["id"],
            "name": "新温度",
            "type": "temperature",
        },
    )
    new_sensor = response.json()["entities"][-1]
    assert new_sensor["state"]["temperature_c"] > 28
    assert response.json()["rooms"][0]["temperature_c"] is None
    response = client.patch(
        f"/simulation/rooms/{room['id']}",
        json={
            "primary_temperature_entity_id": new_sensor["id"],
        },
    )
    assert response.json()["rooms"][0]["temperature_c"] == new_sensor["state"]["temperature_c"]
    occupancy = entity(initial, "occupancy")
    client.patch(f"/simulation/rooms/{room['id']}", json={"primary_occupancy_entity_id": None})
    event(client, occupancy, occupied=True)
    assert snapshot(client)["rooms"][0]["occupied"] is None


@pytest.mark.parametrize(
    "kind,config,expected",
    [
        ("light", {"default_brightness_pct": 88}, {"power": False, "brightness_pct": 0}),
        (
            "climate",
            {"initial_target_temperature_c": 22},
            {
                "mode": "off",
                "target_temperature_c": 22,
                "fan_mode": "auto",
                "hvac_action": "off",
            },
        ),
        ("cover", {"initial_position_pct": 12}, {"position_pct": 12}),
        ("occupancy", {"initial_occupied": True}, {"occupied": True}),
        ("window", {"initial_open": True}, {"window_open": True}),
    ],
)
def test_reset_uses_saved_type_specific_preferences(client, kind, config, expected):
    target = entity(snapshot(client), kind)
    client.patch(f"/simulation/entities/{target['id']}", json={"config": config})
    event(client, target, known=False, available=False)
    reset = client.post("/simulation/reset", json={}).json()
    result = by_id(reset, target["id"])
    assert result["state"] == expected
    assert result["known"] is True and result["available"] is True
    if kind == "light":
        control(client, target, "set_light", {"power": True})
        assert by_id(snapshot(client), target["id"])["state"]["brightness_pct"] == 88


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/simulation/rooms", {"name": " "}),
        ("post", "/simulation/rooms", {"name": "房", "initial_temperature_c": True}),
        ("post", "/simulation/rooms", {"name": "房", "initial_temperature_c": None}),
        ("post", "/simulation/rooms", {"name": "房", "home_id": "another-home"}),
        ("patch", "/simulation/rooms/{room}", {}),
        ("patch", "/simulation/rooms/{room}", {"name": None}),
        ("patch", "/simulation/entities/{entity}", {"type": "climate"}),
        ("patch", "/simulation/entities/{entity}", {"enabled": 1}),
        ("patch", "/simulation/entities/{entity}", {"config": None}),
        ("post", "/simulation/faults/{entity}", {"mode": "delayed", "delay_minutes": True}),
        ("post", "/simulation/faults/{entity}", {"mode": "delayed", "delay_minutes": 0}),
        ("post", "/simulation/faults/{entity}", {"mode": "invented"}),
        ("post", "/simulation/reset", {"restore_template": True}),
    ],
)
def test_invalid_structural_requests_leave_world_untouched(client, method, path, body):
    initial = snapshot(client)
    path = path.format(room=initial["rooms"][0]["id"], entity=entity(initial, "light")["id"])
    response = getattr(client, method)(path, json=body)
    assert response.status_code == 422, response.text
    assert snapshot(client) == initial


def test_unknown_readback_result_is_independently_recoverable(client):
    light = entity(snapshot(client), "light")
    event(client, light, known=False)
    response = control(client, light, "set_light", {"power": True})
    assert response.json()["outcome"] == "unknown"
    assert by_id(snapshot(client), light["id"])["state"]["power"] is None
    event(client, light, known=True)
    assert by_id(snapshot(client), light["id"])["state"]["power"] is True


def test_long_advance_is_valid_without_wall_clock_delay(client):
    assert advance(client, 1440)["simulated_minutes"] == 1440
