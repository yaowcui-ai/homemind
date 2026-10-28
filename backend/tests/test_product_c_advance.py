"""Protected task-clock requests survive response loss and database reconstruction."""

from conftest import authenticated_client
from fastapi.testclient import TestClient

from homemind.app import create_app
from homemind.persistence.database import Database


def snapshot(client):
    return client.get("/simulation").json()


def sleeping(client):
    before = snapshot(client)
    response = client.post(
        "/tasks",
        json={
            "scenario": "sleep",
            "room_ids": [before["rooms"][0]["id"]],
            "target_temperature_c": 18,
        },
        headers={"Idempotency-Key": "sleep-product-c"},
    )
    assert response.status_code == 200, response.text
    task = response.json()
    return task, {"expected_world_id": before["world_id"], "expected_simulated_minutes": 0}


def advance(client, task, body, key="advance-product-c"):
    return client.post(
        "/tasks/" + task["id"] + "/advance", json=body, headers={"Idempotency-Key": key}
    )


def test_protected_sleep_replay_persists_and_reset_replay_is_read_only(client):
    task, body = sleeping(client)
    first = advance(client, task, body)
    assert first.status_code == 200, first.text
    assert first.json()["final_snapshot"]["simulated_minutes"] == 10
    assert first.json()["advance_records"][0]["key"] == "advance-product-c"
    assert first.json()["actions"] == task["actions"]
    database = client.app.state.database
    rebuilt = create_app(
        client.app.state.settings,
        database=Database(str(database.engine.url), instance_id=database.instance_id),
    )
    with TestClient(rebuilt) as restarted:
        restarted.cookies.update(client.cookies)
        restarted.headers.update(client.headers)
        assert advance(restarted, task, body).json() == first.json()
        assert snapshot(restarted)["simulated_minutes"] == 10
        reset = restarted.post("/simulation/reset", json={})
        assert reset.status_code == 200, reset.text
        before = snapshot(restarted)
        assert advance(restarted, task, body).json() == first.json()
        assert snapshot(restarted) == before


def test_old_time_new_key_and_same_key_different_body_never_advance(client):
    task, body = sleeping(client)
    assert advance(client, task, body).status_code == 200
    before = snapshot(client)
    conflict = advance(client, task, {**body, "expected_simulated_minutes": 10})
    assert (
        conflict.status_code == 409 and conflict.json()["detail"]["code"] == "idempotency_conflict"
    )
    stale = advance(client, task, body, "advance-other-key")
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "clock_changed"
    assert snapshot(client) == before


def test_partial_protection_rejected_and_legacy_empty_remains_compatible(client):
    task, body = sleeping(client)
    assert client.post("/tasks/" + task["id"] + "/advance", json=body).status_code == 422
    assert advance(client, task, {}).status_code == 422
    assert snapshot(client)["simulated_minutes"] == 0
    assert client.post("/tasks/" + task["id"] + "/advance", json={}).status_code == 200


def test_replay_returns_original_evidence_after_later_advance_without_nested_results(client):
    task, body = sleeping(client)
    first = advance(client, task, body).json()
    second = advance(client, task, {**body, "expected_simulated_minutes": 10}, "advance-second-key")
    assert second.status_code == 200, second.text
    assert second.json()["final_snapshot"]["simulated_minutes"] == 20
    before = snapshot(client)
    assert advance(client, task, body).json() == first
    assert snapshot(client) == before
    records = client.get("/tasks/" + task["id"]).json()["advance_records"]
    assert len(records) == 2 and all(
        set(r) == {"key", "request", "advanced_to_minutes"} for r in records
    )


def test_modern_advance_preserves_home_isolation_world_and_debug_gates(client, tmp_path):
    task, body = sleeping(client)
    assert advance(client, task, {**body, "expected_world_id": "other-world"}).status_code == 409
    assert advance(client, task, {**body, "expected_simulated_minutes": True}).status_code == 422
    assert snapshot(client)["simulated_minutes"] == 0
    with authenticated_client(tmp_path / "unused.db", database=client.app.state.database) as other:
        assert advance(other, task, body).status_code == 404
        assert other.get("/tasks/" + task["id"]).status_code == 404
        assert snapshot(other)["simulated_minutes"] == 0
    client.app.state.settings.simulation_debug_enabled = False
    assert advance(client, task, body).status_code == 403
    client.app.state.settings.simulation_debug_enabled = True
    assert advance(client, task, body).status_code == 200


def test_protected_homecoming_retains_exact_deadline_evidence_and_never_resends_actions(client):
    before = snapshot(client)
    created = client.post(
        "/tasks",
        json={
            "scenario": "homecoming",
            "room_ids": [before["rooms"][0]["id"]],
            "ready_in_minutes": 60,
        },
        headers={"Idempotency-Key": "c-homecoming-deadline"},
    )
    assert created.status_code == 200, created.text
    task = created.json()
    body = {"expected_world_id": before["world_id"], "expected_simulated_minutes": 0}
    result = advance(client, task, body)
    assert result.status_code == 200, result.text
    assert result.json()["verification"]["checked_at_minutes"] == 60
    assert result.json()["verification"]["due_at_minutes"] == 60
    assert result.json()["status"] == "succeeded"
    assert result.json()["actions"] == task["actions"]
    assert advance(client, task, body).json() == result.json()
    assert snapshot(client)["simulated_minutes"] == 60
