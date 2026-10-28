"""Offline rejected-output evidence through the actual graph, API and persistence."""

import json

import pytest
from test_m4_agent import ScriptedModel, cooling, home, plan, submit


@pytest.mark.parametrize(
    "field,reference_kind,path",
    [
        ("option", "entity", "$.options[0].id"),
        ("room_option", "room", "$.options[0].id"),
        ("action", "entity", "$.actions[0].entity_id"),
        ("action_room", "room", "$.actions[0].room_id"),
        ("room", "room", "$.room_ids[0]"),
        ("protected", "room", "$.protected_room_ids[0]"),
        ("keep", "entity", "$.keep_entity_ids[0]"),
        ("temperature", "room", "$.temperatures[0].room_id"),
    ],
)
def test_invalid_reference_identifies_rejected_field_without_persisting_model_text(
    client, field, reference_kind, path
):
    before = home(client)
    unknown = "confirm_closed_private_model_value"
    output = plan(before)
    if field in {"option", "room_option"}:
        output = {
            "kind": "clarify",
            "question": "unvalidated private question",
            "options": [{"id": unknown, "kind": reference_kind, "label": "private label"}],
        }
    elif field == "action":
        output["actions"][0]["entity_id"] = unknown
    elif field == "action_room":
        output["actions"][0]["room_id"] = unknown
    elif field == "room":
        output["room_ids"] = [unknown]
    elif field == "protected":
        output["protected_room_ids"] = [unknown]
    elif field == "keep":
        output["keep_entity_ids"] = [unknown]
    else:
        output = cooling(before)
        output["temperatures"][0]["room_id"] = unknown
    output["rationale"] = "private rationale" if output["kind"] == "plan" else None
    if output["kind"] == "clarify":
        del output["rationale"]
    response = submit(client, ScriptedModel(output))
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["status"] == "failed" and task["actions"] == []
    assert task["agent_run"]["diagnostic"] == {
        "phase": "validation",
        "output_kind": output["kind"],
        "code": "not_found",
        "field_path": path,
        "reference_kind": reference_kind,
        "reference_in_current_home": False,
    }
    assert task["agent_run"]["failure_code"] == "not_found"
    serialized = json.dumps(task)
    for private in (unknown, "private label", "private rationale", "unvalidated private question"):
        assert private not in serialized
    assert task["agent_run"]["proposed_plan"] is None
    assert client.get(f"/tasks/{task['id']}").json() == task
    assert submit(client, ScriptedModel()).json() == task
    assert home(client) == before


def test_control_failure_and_window_failure_have_distinct_paths(client):
    before = home(client)
    output = plan(before)
    output["actions"][0]["parameters"] = {"brightness_pct": 101}
    task = submit(client, ScriptedModel(output)).json()
    diagnostic = task["agent_run"]["diagnostic"]
    assert diagnostic["field_path"] == "$.actions[0].parameters"
    assert diagnostic["reference_in_current_home"] is True
    assert diagnostic["code"] == task["agent_run"]["failure_code"]
    window = next(e for e in before["entities"] if e["type"] == "window")
    client.post("/simulation/events", json={"entity_id": window["id"], "known": False})
    task = submit(client, ScriptedModel(cooling(home(client))), key="window-unknown-123").json()
    diagnostic = task["agent_run"]["diagnostic"]
    assert diagnostic["code"] == "window_not_closed"
    assert diagnostic["field_path"] == "$.actions[1].parameters"
    assert task["actions"] == []


def test_unsupported_action_points_to_action_rather_than_parameters(client):
    before = home(client)
    output = plan(before)
    output["actions"][0]["action"] = "set_cover"
    task = submit(client, ScriptedModel(output)).json()
    assert task["agent_run"]["diagnostic"]["code"] == "unsupported_action"
    assert task["agent_run"]["diagnostic"]["field_path"] == "$.actions[0].action"
    assert task["actions"] == [] and home(client) == before


@pytest.mark.parametrize(
    "field,code,path",
    [
        ("duplicate", "duplicate_reference", "$.room_ids"),
        ("omitted_keep", "constraint_omitted", "$.keep_entity_ids"),
        ("wrong_scope", "invalid_scope", "$.actions[0].room_id"),
        ("kept_action", "protected_conflict", "$.actions[0].entity_id"),
        ("wrong_temperature", "invalid_goal", "$.temperatures[0].target"),
    ],
)
def test_existing_constraints_keep_precise_failure_location(client, field, code, path):
    before = home(client)
    output = plan(before)
    body = {"text": "按指定需求操作", "expected_world_id": before["world_id"]}
    if field == "duplicate":
        output["room_ids"] *= 2
    elif field == "omitted_keep":
        body["keep_entity_ids"] = [output["actions"][0]["entity_id"]]
    elif field == "wrong_scope":
        output["actions"][0]["room_id"] = before["rooms"][1]["id"]
    elif field == "kept_action":
        output["keep_entity_ids"] = [output["actions"][0]["entity_id"]]
    else:
        output = cooling(before)
        output["temperatures"][0]["target"] = 25
    task = submit(client, ScriptedModel(output), body=body).json()
    diagnostic = task["agent_run"]["diagnostic"]
    assert diagnostic["code"] == code and diagnostic["field_path"] == path
    assert task["actions"] == [] and home(client) == before


def test_foreign_reference_is_only_checked_against_current_home(tmp_path):
    from conftest import authenticated_client

    from homemind.persistence.database import Database

    path = tmp_path / "shared.db"
    database = Database(
        f"sqlite+aiosqlite:///{path}", instance_id="unit-installation", initialize_test=True
    )
    with authenticated_client(path, database=database) as first:
        foreign = next(e for e in home(first)["entities"] if e["type"] == "light")
        first.patch("/simulation/entities/" + foreign["id"], json={"name": "other-home-private"})
        with authenticated_client(path, database=database) as second:
            before = home(second)
            output = plan(before)
            output["actions"][0]["entity_id"] = foreign["id"]
            task = submit(second, ScriptedModel(output)).json()
            assert task["agent_run"]["diagnostic"]["reference_in_current_home"] is False
            assert foreign["id"] not in json.dumps(task)
            assert "other-home-private" not in json.dumps(task)
            assert task["actions"] == [] and home(second) == before
