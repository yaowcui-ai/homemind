"""Rule baseline contracts through the real authenticated API."""

import pytest


def state(client):
    response = client.get("/simulation")
    assert response.status_code == 200, response.text
    return response.json()


def post_task(client, body, key="task-key-12345"):
    return client.post("/tasks", json=body, headers={"Idempotency-Key": key})


def body(client, scenario="homecoming", **extra):
    return {"scenario": scenario, "room_ids": [state(client)["rooms"][0]["id"]], **extra}


def test_homecoming_inline_actions_due_verification_and_idempotency(client):
    initial = state(client)
    request = body(client, ready_in_minutes=60)
    response = post_task(client, request)
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["status"] == "waiting_verification"
    assert task["verification"]["due_at_minutes"] == 60
    assert task["request"]["target_temperature_c"] == 26
    assert task["request"]["ready_in_minutes"] == 60
    assert task["preferences_snapshot"]["version"] == 1
    assert len(task["actions"]) == 3
    assert all(a["status"] == "verified" for a in task["actions"])
    assert task["initial_snapshot"] == initial
    assert post_task(client, request).json() == task
    assert state(client) == task["final_snapshot"]
    assert len(client.get("/tasks").json()) == 1
    assert post_task(client, {**request, "target_temperature_c": 25}).status_code == 409
    client.patch("/preferences", json={"comfort_temperature_c": 24})
    assert post_task(client, request).json()["id"] == task["id"]
    assert (
        client.get(f"/tasks/{task['id']}").json()["preferences_snapshot"]["comfort_temperature_c"]
        == 26
    )
    client.post("/simulation/advance", json={"minutes": 60})
    verified = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert verified["status"] == "succeeded", verified
    assert verified["actions"] == task["actions"]
    assert state(client)["revision"] == task["final_snapshot"]["revision"] + 1


@pytest.mark.parametrize("scenario", ["sleep", "away"])
def test_sleep_and_away_discover_all_devices_and_keep_other_rooms(client, scenario):
    before = state(client)
    room_id = before["rooms"][0]["id"]
    added = client.post(
        "/simulation/entities",
        json={
            "room_id": room_id,
            "name": "第二盏灯",
            "type": "light",
            "config": {"default_brightness_pct": 75},
        },
    ).json()
    second = added["entities"][-1]
    client.post(
        f"/simulation/controls/{second['id']}",
        json={"action": "set_light", "parameters": {"power": True}},
    )
    other_entities = [e for e in before["entities"] if e["room_id"] != room_id]
    response = post_task(client, body(client, scenario))
    assert response.status_code == 200, response.text
    task = response.json()
    assert len(task["actions"]) == 4
    assert (
        next(e for e in task["final_snapshot"]["entities"] if e["id"] == second["id"])["state"][
            "power"
        ]
        is False
    )
    assert [
        e for e in task["final_snapshot"]["entities"] if e["room_id"] != room_id
    ] == other_entities
    assert task["status"] == ("waiting_verification" if scenario == "sleep" else "succeeded")


def test_keep_protect_window_and_missing_readings_never_fake_success(client):
    initial = state(client)
    room = initial["rooms"][0]
    light = next(
        e for e in initial["entities"] if e["room_id"] == room["id"] and e["type"] == "light"
    )
    window = next(
        e for e in initial["entities"] if e["room_id"] == room["id"] and e["type"] == "window"
    )
    client.post("/simulation/events", json={"entity_id": window["id"], "window_open": True})
    request = body(client, keep_entity_ids=[light["id"]])
    response = post_task(client, request)
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["status"] == "partial"
    assert all(a["entity_id"] != light["id"] for a in task["actions"])
    assert all(a["action"] != "set_climate" for a in task["actions"])
    assert any("窗" in condition["message"] for condition in task["verification"]["conditions"])
    assert (
        post_task(client, body(client, protected_room_ids=[room["id"]]), "conflict-123").status_code
        == 422
    )
    client.delete(f"/simulation/entities/{room['primary_temperature_entity_id']}")
    missing = post_task(client, body(client, "sleep"), "missing-sensor-123").json()
    assert missing["status"] in {"partial", "failed"}
    assert any(c["outcome"] == "unknown" for c in missing["verification"]["conditions"])


@pytest.mark.parametrize(
    "extra",
    [
        {"target_temperature_c": 15},
        {"target_temperature_c": 26.5},
        {"ready_in_minutes": 0},
        {"room_ids": []},
        {"home_id": "foreign"},
        {"room_ids": ["missing"]},
        {"keep_entity_ids": ["missing"]},
    ],
)
def test_invalid_rule_requests_do_not_mutate_home(client, extra):
    before = state(client)
    response = post_task(client, body(client, **extra))
    assert response.status_code in {404, 422}, response.text
    assert state(client) == before
    assert client.get("/tasks").json() == []


def test_away_rejects_irrelevant_parameters_and_old_world(client):
    assert post_task(client, body(client, "away", target_temperature_c=26)).status_code == 422
    assert post_task(client, body(client, "sleep", ready_in_minutes=20)).status_code == 422
    assert post_task(client, body(client, expected_world_id="old-world")).status_code == 409


def test_task_verification_after_reset_does_not_send_actions(client):
    task = post_task(client, body(client)).json()
    reset = client.post("/simulation/reset", json={}).json()
    verified = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert verified["status"] == "failed"
    assert any("重置" in c["message"] for c in verified["verification"]["conditions"])
    assert state(client) == reset


def test_lost_response_and_unknown_reading_are_separate(client):
    before = state(client)
    light = next(e for e in before["entities"] if e["type"] == "light")
    client.post(f"/simulation/faults/{light['id']}", json={"mode": "response_lost"})
    task = post_task(client, body(client, "away")).json()
    action = next(a for a in task["actions"] if a["entity_id"] == light["id"])
    assert action["status"] == "verified" and action["transport_outcome"] == "unknown"
    client.post("/simulation/events", json={"entity_id": light["id"], "known": False})
    task = post_task(client, body(client, "away"), "unknown-task-123").json()
    assert task["status"] == "partial"
    action = next(a for a in task["actions"] if a["entity_id"] == light["id"])
    assert action["status"] == "unknown"


def test_busy_claim_replay_and_idempotency_key_rules(client):
    request = body(client, "away")
    assert client.post("/tasks", json=request).status_code == 422
    task = post_task(client, request).json()
    database = client.app.state.database
    home_id = state(client)["home_id"]
    database.busy.add(home_id)
    try:
        assert post_task(client, request).json()["id"] == task["id"]
        assert post_task(client, request, "different-key-123").status_code == 409
    finally:
        database.busy.remove(home_id)


def test_rollback_does_not_publish_partial_simulation_or_tasks(client, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    from homemind.simulation.service import SimulationService

    before = state(client)
    original = SimulationService.control
    count = 0

    def interrupt(self, entity_id, request):
        nonlocal count
        count += 1
        if count == 2:
            raise SQLAlchemyError("synthetic interruption; must never appear in response")
        return original(self, entity_id, request)

    monkeypatch.setattr(SimulationService, "control", interrupt)
    response = post_task(client, body(client))
    assert response.status_code == 503
    assert "synthetic" not in response.text
    assert state(client) == before
    assert client.get("/tasks").json() == []
    assert before["home_id"] not in client.app.state.database.busy


def test_temperature_recovery_uses_current_independent_observation(client):
    before = state(client)
    room = before["rooms"][0]
    sensor_id = room["primary_temperature_entity_id"]
    client.post("/simulation/events", json={"entity_id": sensor_id, "known": False})
    task = post_task(client, body(client, "sleep")).json()
    assert task["status"] == "partial"
    client.post(
        "/simulation/events", json={"entity_id": sensor_id, "known": True, "temperature_c": 26.0}
    )
    recovered = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert recovered["status"] == "succeeded", recovered


def test_moved_entity_does_not_verify_old_room_plan(client):
    initial = state(client)
    task = post_task(client, body(client)).json()
    entity_id = task["actions"][0]["entity_id"]
    client.patch(f"/simulation/entities/{entity_id}", json={"room_id": initial["rooms"][1]["id"]})
    verified = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert verified["status"] == "partial"
    assert any("房间" in c["message"] for c in verified["verification"]["conditions"])


def test_late_temperature_achievement_does_not_prove_deadline(client):
    task = post_task(client, body(client)).json()
    assert task["verification"]["due_at_minutes"] == 20
    assert task["request"]["ready_in_minutes"] == 20
    client.post("/simulation/advance", json={"minutes": 60})
    response = client.post(f"/tasks/{task['id']}/verify", json={})
    assert response.status_code == 200
    checked = response.json()
    assert checked["status"] == "partial"
    goal = checked["verification"]["conditions"][-1]
    assert goal["outcome"] == "unknown"
    assert "超过目标时刻" in goal["message"]
    assert "缺少该时刻读数" in goal["message"]


def test_exact_deadline_failure_remains_failure_after_later_cooling(client):
    task = post_task(client, body(client)).json()
    client.post("/simulation/advance", json={"minutes": 20})
    at_deadline = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert at_deadline["status"] == "partial"
    assert at_deadline["verification"]["conditions"][-1]["outcome"] == "failed"
    client.post("/simulation/advance", json={"minutes": 40})
    late = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert late["status"] == "partial"
    assert late["verification"]["conditions"][-1]["outcome"] == "failed"
    again = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert again["status"] == "partial"
    assert again["verification"]["conditions"][-1]["outcome"] == "failed"


def test_exact_deadline_success_survives_repeated_later_verification(client):
    task = post_task(client, body(client, ready_in_minutes=60)).json()
    client.post("/simulation/advance", json={"minutes": 60})
    at_deadline = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert at_deadline["status"] == "succeeded"
    client.post("/simulation/advance", json={"minutes": 10})
    before_verify = state(client)
    for _ in range(2):
        later = client.post(f"/tasks/{task['id']}/verify", json={}).json()
        assert later["status"] == "succeeded"
        assert later["verification"]["conditions"][-1]["outcome"] == "verified"
    assert state(client) == before_verify


def test_early_achievement_waits_for_explicit_deadline(client):
    initial = state(client)
    sensor_id = initial["rooms"][0]["primary_temperature_entity_id"]
    client.post("/simulation/events", json={"entity_id": sensor_id, "temperature_c": 26.0})
    task = post_task(client, body(client)).json()
    assert task["status"] == "waiting_verification"
    assert (
        client.post(f"/tasks/{task['id']}/verify", json={}).json()["status"]
        == "waiting_verification"
    )


def test_recorded_deadline_evidence_is_not_replaced_by_same_minute_changes(client):
    task = post_task(client, body(client)).json()
    client.post("/simulation/advance", json={"minutes": 20})
    first = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert first["verification"]["conditions"][-1]["outcome"] == "failed"
    sensor_id = state(client)["rooms"][0]["primary_temperature_entity_id"]
    client.post("/simulation/events", json={"entity_id": sensor_id, "temperature_c": 26.0})
    repeated = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert repeated["status"] == "partial"
    assert repeated["verification"]["conditions"][-1]["outcome"] == "failed"


def test_succeeded_task_verify_preserves_terminal_history_after_manual_changes(client):
    task = post_task(client, body(client, "away")).json()
    assert task["status"] == "succeeded"
    light = next(e for e in state(client)["entities"] if e["type"] == "light")
    client.post(
        f"/simulation/controls/{light['id']}",
        json={"action": "set_light", "parameters": {"power": True}},
    )
    client.post("/simulation/advance", json={"minutes": 3})
    current = state(client)
    repeated = client.post(f"/tasks/{task['id']}/verify", json={})
    assert repeated.status_code == 200
    assert repeated.json() == task
    assert client.get(f"/tasks/{task['id']}").json() == task
    assert state(client) == current
    client.post("/simulation/reset", json={})
    assert client.post(f"/tasks/{task['id']}/verify", json={}).json() == task
