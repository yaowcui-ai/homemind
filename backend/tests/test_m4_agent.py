"""Explicitly injected model tests exercise actual graph and authenticated APIs."""

import json

import pytest
from langchain_core.messages import AIMessage


class ScriptedModel:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def ainvoke(self, messages, tools):
        self.calls.append((messages, tools))
        result = self.responses.pop(0)
        if callable(result):
            result = await result()
        if isinstance(result, Exception):
            raise result
        return result if isinstance(result, AIMessage) else AIMessage(content=json.dumps(result))


def home(client):
    return client.get("/simulation").json()


def plan(snapshot, scenario="local", all_rooms=False, **extra):
    rooms = snapshot["rooms"] if all_rooms else snapshot["rooms"][:1]
    ids = [r["id"] for r in rooms]
    lights = [e for e in snapshot["entities"] if e["type"] == "light" and e["room_id"] in ids]
    result = dict(
        kind="plan",
        scenario=scenario,
        room_ids=ids,
        keep_entity_ids=[],
        protected_room_ids=[],
        actions=[
            dict(
                entity_id=e["id"],
                room_id=e["room_id"],
                action="set_light",
                parameters={"power": True},
            )
            for e in lights
        ],
        temperatures=[],
        ready_in_minutes=None,
        rationale="按明确的房间操作灯",
    )
    result.update(extra)
    if scenario == "away":
        for action in result["actions"]:
            action["parameters"] = {"power": False}
    return result


def submit(client, model, body=None, key="agent-create-123"):
    client.app.state.agent_model = model
    return client.post(
        "/tasks/agent",
        json=body or {"text": "打开指定灯", "expected_world_id": home(client)["world_id"]},
        headers={"Idempotency-Key": key},
    )


def test_single_light_real_graph_and_recovery(client):
    before = home(client)
    reads = AIMessage(
        content="",
        tool_calls=[{"id": "read1", "name": "read_home", "args": {}, "type": "tool_call"}],
    )
    model = ScriptedModel(reads, plan(before))
    response = submit(client, model)
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["mode"] == "single_agent" and task["status"] == "succeeded"
    assert len(task["actions"]) == 1 and task["actions"][0]["status"] == "verified"
    assert task["agent_run"]["model_calls"] == 2 and task["agent_run"]["tool_calls"] == 1
    assert task["agent_run"]["usage"] is None
    assert len(client.get("/tasks?submission_key=agent-create-123").json()) == 1
    assert client.get("/tasks?submission_key=missing-key").json() == []
    assert submit(client, model).json()["id"] == task["id"] and len(model.calls) == 2
    assert (
        submit(
            client, model, {"text": "另一个需求", "expected_world_id": before["world_id"]}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/tasks",
            json={"scenario": "away", "room_ids": [before["rooms"][0]["id"]]},
            headers={"Idempotency-Key": "agent-create-123"},
        ).status_code
        == 409
    )


def test_clarification_same_id_idempotency_and_verify_guard(client):
    before = home(client)
    question = {
        "kind": "clarify",
        "question": "请选择房间",
        "options": [{"id": r["id"], "label": r["name"], "kind": "room"} for r in before["rooms"]],
    }
    model = ScriptedModel(question, plan(before))
    first = submit(client, model).json()
    assert first["status"] == "waiting_input"
    assert client.post(f"/tasks/{first['id']}/verify", json={}).json()["status"] == "waiting_input"
    url = f"/tasks/{first['id']}/reply"
    reply = {"text": "第一个房间", "expected_turn": 0}
    headers = {"Idempotency-Key": "reply-key-123"}
    next_task = client.post(url, json=reply, headers=headers)
    assert next_task.status_code == 200, next_task.text
    assert next_task.json()["id"] == first["id"] and next_task.json()["agent_run"]["turn"] == 1
    assert next_task.json()["status"] == "succeeded"
    assert client.post(url, json=reply, headers=headers).json() == next_task.json()
    assert (
        client.post(url, json=reply, headers={"Idempotency-Key": "another-reply-123"}).status_code
        == 409
    )
    assert len(model.calls) == 2


def test_confirmation_is_explicit_idempotent(client):
    before = home(client)
    model = ScriptedModel(plan(before, "away", all_rooms=True))
    task = submit(client, model).json()
    assert task["status"] == "waiting_confirmation" and task["actions"] == []
    assert home(client) == before
    assert (
        client.post(f"/tasks/{task['id']}/verify", json={}).json()["status"]
        == "waiting_confirmation"
    )
    url = f"/tasks/{task['id']}/confirm"
    headers = {"Idempotency-Key": "confirmation-123"}
    assert client.post(url, json={"expected_turn": 1}, headers=headers).status_code == 409
    confirmed = client.post(url, json={"expected_turn": 0}, headers=headers)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "succeeded"
    assert client.post(url, json={"expected_turn": 0}, headers=headers).json() == confirmed.json()
    assert len(model.calls) == 1


def test_stale_confirmation_does_not_execute(client):
    task = submit(client, ScriptedModel(plan(home(client), "away", all_rooms=True))).json()
    client.patch("/simulation/rooms/" + home(client)["rooms"][0]["id"], json={"name": "新名字"})
    before = home(client)
    response = client.post(
        f"/tasks/{task['id']}/confirm",
        json={"expected_turn": 0},
        headers={"Idempotency-Key": "confirmation-123"},
    )
    assert response.status_code == 200
    assert (
        response.json()["status"] == "failed"
        and response.json()["agent_run"]["failure_code"] == "state_changed"
    )
    assert home(client) == before


@pytest.mark.parametrize(
    "mutation",
    [
        "fiction",
        "foreign_room",
        "sensor",
        "extra",
        "empty",
        "duplicate",
        "range",
        "conflicting",
        "protected",
        "kept",
    ],
)
def test_invalid_plans_checked_before_first_action(client, mutation):
    before = home(client)
    result = plan(before)
    action = result["actions"][0]
    if mutation == "fiction":
        action["entity_id"] = "fiction"
    if mutation == "foreign_room":
        action["room_id"] = "foreign-room"
    if mutation == "sensor":
        action["entity_id"] = before["rooms"][0]["primary_temperature_entity_id"]
    if mutation == "extra":
        result["write_database"] = "yes"
    if mutation == "empty":
        result["actions"] = []
    if mutation == "duplicate":
        result["actions"].append(dict(action))
    if mutation == "range":
        action["parameters"] = {"brightness_pct": 101}
    if mutation == "conflicting":
        action["parameters"] = {"power": False, "brightness_pct": 50}
    if mutation == "protected":
        result["protected_room_ids"] = result["room_ids"]
    if mutation == "kept":
        result["keep_entity_ids"] = [action["entity_id"]]
    task = submit(client, ScriptedModel(result)).json()
    assert task["status"] == "failed", task
    assert task["actions"] == [] and home(client) == before
    assert client.post(f"/tasks/{task['id']}/verify", json={}).json()["status"] == "failed"


def cooling(snapshot, scenario="homecoming"):
    result = plan(snapshot, scenario)
    room = snapshot["rooms"][0]
    climate = next(
        e for e in snapshot["entities"] if e["room_id"] == room["id"] and e["type"] == "climate"
    )
    result["actions"].append(
        {
            "entity_id": climate["id"],
            "room_id": room["id"],
            "action": "set_climate",
            "parameters": {"mode": "cool", "target_temperature_c": 26, "fan_mode": "auto"},
        }
    )
    result["temperatures"] = [{"room_id": room["id"], "target": 26}]
    result["ready_in_minutes"] = 60 if scenario == "homecoming" else None
    return result


@pytest.mark.parametrize("scenario", ["homecoming", "sleep"])
def test_temperature_scenarios_advance_atomically(client, scenario):
    task = submit(client, ScriptedModel(cooling(home(client), scenario))).json()
    assert task["status"] == "waiting_verification", task
    response = client.post(f"/tasks/{task['id']}/advance", json={})
    assert response.status_code == 200, response.text
    checked = response.json()
    assert checked["final_snapshot"]["simulated_minutes"] == (
        60 if scenario == "homecoming" else 10
    )
    if scenario == "homecoming":
        assert checked["status"] == "succeeded"
        assert checked["plan"]["deadline_evidence"]
        assert client.post(f"/tasks/{task['id']}/advance", json={}).status_code == 409


@pytest.mark.parametrize("unknown", [False, True])
def test_window_open_or_unknown_refuses_entire_plan(client, unknown):
    snapshot = home(client)
    window = next(e for e in snapshot["entities"] if e["type"] == "window")
    client.post(
        "/simulation/events",
        json={
            "entity_id": window["id"],
            **({"known": False} if unknown else {"window_open": True}),
        },
    )
    before = home(client)
    task = submit(client, ScriptedModel(cooling(before))).json()
    assert task["status"] == "failed" and not task["actions"] and home(client) == before


@pytest.mark.parametrize(
    "response,code",
    [
        (
            AIMessage(
                content="",
                tool_calls=[{"id": "bad", "name": "write_home", "args": {}, "type": "tool_call"}],
            ),
            "invalid_tool",
        ),
        (
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "bad",
                        "name": "read_home",
                        "args": {"home_id": "foreign"},
                        "type": "tool_call",
                    }
                ],
            ),
            "invalid_tool",
        ),
        (TimeoutError("secret provider detail"), "model_timeout"),
        (RuntimeError("secret provider detail"), "model_unavailable"),
        ("not-json", "invalid_output"),
    ],
)
def test_safe_failures_no_busy_leaks(client, response, code):
    before = home(client)
    task = submit(client, ScriptedModel(response)).json()
    assert task["status"] == "failed" and task["agent_run"]["failure_code"] == code, task
    assert "secret provider" not in json.dumps(task) and home(client) == before
    assert before["home_id"] not in client.app.state.database.busy


def test_model_budget_real_graph_loop(client):
    reads = AIMessage(
        content="",
        tool_calls=[{"id": "read", "name": "read_home", "args": {}, "type": "tool_call"}],
    )
    model = ScriptedModel(reads, reads, reads)
    task = submit(client, model).json()
    assert task["status"] == "failed" and task["agent_run"]["failure_code"] == "model_budget"
    assert len(model.calls) == 3 and not task["actions"]


def test_public_config_unavailable_without_explicit_model(client):
    response = client.get("/tasks/agent/config")
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.headers["cache-control"] == "no-store"
    assert submit(client, None).status_code == 503


def test_debug_disabled_blocks_waiting_goals_but_allows_local(tmp_path):
    from conftest import authenticated_client

    with authenticated_client(tmp_path / "plain.db", debug=False) as client:
        for scenario in ("homecoming", "sleep"):
            before = home(client)
            task = submit(
                client, ScriptedModel(cooling(before, scenario)), key="debug-" + scenario
            ).json()
            assert (
                task["status"] == "failed"
                and task["agent_run"]["failure_code"] == "simulation_debug_required"
            )
            assert not task["actions"] and home(client) == before
            assert client.post(f"/tasks/{task['id']}/advance", json={}).status_code == 403
        assert (
            submit(client, ScriptedModel(plan(home(client))), key="local-light-123").json()[
                "status"
            ]
            == "succeeded"
        )


def test_cross_account_cannot_read_reply_confirm_or_recover(tmp_path):
    from conftest import authenticated_client

    from homemind.persistence.database import Database

    path = tmp_path / "shared.db"
    database = Database(
        f"sqlite+aiosqlite:///{path}", instance_id="unit-installation", initialize_test=True
    )
    with authenticated_client(path, database=database) as first:
        task = submit(
            first, ScriptedModel({"kind": "clarify", "question": "哪个房间", "options": []})
        ).json()
        with authenticated_client(path, database=database) as second:
            url = f"/tasks/{task['id']}"
            assert second.get(url).status_code == 404
            headers = {"Idempotency-Key": "reply-key-123"}
            assert (
                second.post(
                    url + "/reply", json={"text": "卧室", "expected_turn": 0}, headers=headers
                ).status_code
                == 404
            )
            assert (
                second.post(
                    url + "/confirm", json={"expected_turn": 0}, headers=headers
                ).status_code
                == 404
            )
            assert second.get("/tasks?submission_key=agent-create-123").json() == []


def test_model_runs_without_transaction_and_changed_facts_block_execution(client):
    from homemind.simulation.models import RoomPatch

    before = home(client)
    database = client.app.state.database

    async def change():
        assert before["home_id"] in database.busy
        assert not database.locks[before["home_id"]].locked()
        async with database.home(before["home_id"]) as (_, _, engine):
            engine.patch_room(before["rooms"][0]["id"], RoomPatch(name="模型期间更名"))
        return AIMessage(content=json.dumps(plan(before)))

    task = submit(client, ScriptedModel(change)).json()
    assert task["status"] == "failed" and task["agent_run"]["failure_code"] == "state_changed"
    assert task["actions"] == []
    assert not database.busy


def test_busy_blocks_new_agent_but_saved_create_replays(client):
    before = home(client)
    model = ScriptedModel(plan(before))
    saved = submit(client, model).json()
    database = client.app.state.database
    database.busy.add(before["home_id"])
    try:
        assert submit(client, model).json()["id"] == saved["id"]
        assert submit(client, model, key="new-create-123").status_code == 409
    finally:
        database.busy.clear()


def test_six_tool_budget_and_three_replies(client):
    calls = [{"id": str(i), "name": "read_home", "args": {}, "type": "tool_call"} for i in range(7)]
    task = submit(client, ScriptedModel(AIMessage(content="", tool_calls=calls))).json()
    assert task["agent_run"]["failure_code"] == "tool_budget" and not task["actions"]
    question = {"kind": "clarify", "question": "请补充明确目标", "options": []}
    model = ScriptedModel(question, question, question, question)
    task = submit(client, model, key="clarify-budget-123").json()
    for turn in range(3):
        task = client.post(
            f"/tasks/{task['id']}/reply",
            json={"text": "补充", "expected_turn": turn},
            headers={"Idempotency-Key": f"reply-budget-{turn}"},
        ).json()
    assert task["agent_run"]["turn"] == 3 and task["agent_run"]["failure_code"] == "reply_budget"
    assert task["status"] == "failed" and len(model.calls) == 4
    assert (
        client.post(
            f"/tasks/{task['id']}/reply",
            json={"text": "补充", "expected_turn": 3},
            headers={"Idempotency-Key": "reply-budget-final"},
        ).status_code
        == 409
    )


def test_explicit_keep_protect_never_silently_omitted(client):
    before = home(client)
    light = next(e for e in before["entities"] if e["type"] == "light")
    for extra in ({"keep_entity_ids": [light["id"]]}, {"protected_room_ids": [light["room_id"]]}):
        body = {"text": "开灯", "expected_world_id": before["world_id"], **extra}
        task = submit(
            client, ScriptedModel(plan(before)), body, key="constraint-" + next(iter(extra))
        ).json()
        assert (
            task["status"] == "failed" and task["agent_run"]["failure_code"] == "constraint_omitted"
        )
        assert not task["actions"] and home(client) == before


def test_lost_response_readback_and_verify_never_resends(client):
    before = home(client)
    light = next(e for e in before["entities"] if e["type"] == "light")
    client.post("/simulation/faults/" + light["id"], json={"mode": "response_lost"})
    task = submit(client, ScriptedModel(plan(home(client)))).json()
    assert task["status"] == "succeeded"
    assert (
        task["actions"][0]["status"] == "verified"
        and task["actions"][0]["transport_outcome"] == "unknown"
    )
    snapshot = home(client)
    for _ in range(2):
        assert client.post(f"/tasks/{task['id']}/verify", json={}).json() == task
    assert home(client) == snapshot


def test_advance_does_not_reset_or_backfill_deadline(client):
    task = submit(client, ScriptedModel(cooling(home(client)))).json()
    client.post("/simulation/advance", json={"minutes": 61})
    before = home(client)
    assert client.post(f"/tasks/{task['id']}/advance", json={}).status_code == 409
    assert home(client) == before
    checked = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert (
        checked["status"] == "partial"
        and checked["verification"]["conditions"][-1]["outcome"] == "unknown"
    )
    client.post("/simulation/reset", json={})
    reset = home(client)
    assert client.post(f"/tasks/{task['id']}/advance", json={}).status_code == 409
    assert home(client) == reset


def test_offline_device_entire_plan_blocked(client):
    before = home(client)
    light = next(e for e in before["entities"] if e["type"] == "light")
    client.post("/simulation/faults/" + light["id"], json={"mode": "offline"})
    before = home(client)
    task = submit(client, ScriptedModel(plan(before))).json()
    assert task["status"] == "failed" and not task["actions"] and home(client) == before


def test_same_name_literal_reference_requires_same_task_clarification(client):
    before = home(client)
    room_id = before["rooms"][0]["id"]
    light = next(e for e in before["entities"] if e["type"] == "light")
    client.post(
        "/simulation/entities", json={"room_id": room_id, "name": light["name"], "type": "light"}
    )
    before = home(client)
    guessed = plan(before)
    guessed["actions"] = guessed["actions"][:1]
    model = ScriptedModel(guessed, guessed)
    task = submit(
        client, model, {"text": "打开" + light["name"], "expected_world_id": before["world_id"]}
    ).json()
    assert task["status"] == "waiting_input" and len(task["agent_run"]["options"]) == 2
    checked = client.post(
        f"/tasks/{task['id']}/reply",
        json={"text": "第一个设备 ID " + light["id"], "expected_turn": 0},
        headers={"Idempotency-Key": "reply-name-123"},
    ).json()
    assert checked["id"] == task["id"] and checked["status"] == "succeeded"


def test_temperature_off_parameters_contradictory_and_away_cannot_turn_on(client):
    before = home(client)
    bad = plan(before, "away")
    bad["actions"][0]["parameters"] = {"power": True}
    task = submit(client, ScriptedModel(bad), key="away-invalid-123").json()
    assert task["status"] == "failed" and not task["actions"] and home(client) == before


def test_model_adapter_non_thinking_no_retry_usage_unknown_and_private_fields(client, monkeypatch):
    import asyncio

    import httpx
    from langchain_core.messages import HumanMessage

    from homemind.agent.model import DeepSeekModel
    from homemind.config import Settings

    calls = []

    def respond(request):
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "model": "actual-model",
                "choices": [{"message": {"content": "{}", "reasoning_content": "PRIVATE"}}],
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(respond), **kwargs),
    )
    model = DeepSeekModel(Settings(_env_file=None, model_api_key="synthetic-key"))
    result = asyncio.run(model.ainvoke([HumanMessage(content="test")], []))
    assert calls[0]["thinking"] == {"type": "disabled"} and calls[0]["max_tokens"] == 2048
    assert (
        result.usage_metadata is None and result.response_metadata["model_name"] == "actual-model"
    )
    assert "PRIVATE" not in str(result)


def test_total_timeout_preserves_issued_call_count(client, monkeypatch):
    import asyncio

    from homemind.agent import graph

    monkeypatch.setattr(graph, "ROUND_TIMEOUT_SECONDS", 0.02, raising=False)

    async def blocked():
        await asyncio.sleep(0.3)
        return AIMessage(content="{}")

    model = ScriptedModel(blocked)
    task = submit(client, model).json()
    assert task["agent_run"]["failure_code"] == "round_timeout"
    assert task["agent_run"]["model_calls"] == 1 and len(model.calls) == 1
    assert task["agent_run"]["usage"] is None and not client.app.state.database.busy


def test_dynamic_away_sleep_keep_and_protected_scopes(client):
    before = home(client)
    room = before["rooms"][0]
    client.patch("/simulation/rooms/" + room["id"], json={"name": "工作室"})
    client.post(
        "/simulation/entities", json={"room_id": room["id"], "name": "阅读灯", "type": "light"}
    )
    before = home(client)
    reading = next(e for e in before["entities"] if e["name"] == "阅读灯")
    sleep = cooling(before, "sleep")
    sleep["actions"] = [a for a in sleep["actions"] if a["entity_id"] != reading["id"]]
    sleep["keep_entity_ids"] = [reading["id"]]
    task = submit(client, ScriptedModel(sleep), key="dynamic-sleep-123").json()
    assert task["status"] == "waiting_verification" and all(
        a["entity_id"] != reading["id"] for a in task["actions"]
    )
    before = home(client)
    away = plan(before, "away")
    away["protected_room_ids"] = [before["rooms"][1]["id"]]
    away["actions"] = [
        {
            "entity_id": e["id"],
            "room_id": e["room_id"],
            "action": {"light": "set_light", "climate": "set_climate", "cover": "set_cover"}[
                e["type"]
            ],
            "parameters": {
                "light": {"power": False},
                "climate": {"mode": "off"},
                "cover": {"position_pct": 0},
            }[e["type"]],
        }
        for e in before["entities"]
        if e["room_id"] == room["id"] and e["type"] in {"light", "climate", "cover"}
    ]
    task = submit(client, ScriptedModel(away), key="dynamic-away-123").json()
    assert task["status"] == "waiting_confirmation"
    task = client.post(
        f"/tasks/{task['id']}/confirm",
        json={"expected_turn": 0},
        headers={"Idempotency-Key": "dynamic-confirm-123"},
    ).json()
    assert task["status"] == "succeeded" and len(task["actions"]) == 4
    assert all(a["room_name"] == "工作室" for a in task["actions"])
    protected = [e for e in before["entities"] if e["room_id"] == before["rooms"][1]["id"]]
    assert [
        e for e in home(client)["entities"] if e["room_id"] == before["rooms"][1]["id"]
    ] == protected


def test_clarifying_question_is_preserved_and_sent_to_next_round(client):
    before = home(client)
    question = {
        "kind": "clarify",
        "question": "请选择哪个房间",
        "options": [{"id": before["rooms"][0]["id"], "label": "ignored", "kind": "room"}],
    }
    model = ScriptedModel(question, plan(before))
    waiting = submit(client, model).json()
    task = client.post(
        f"/tasks/{waiting['id']}/reply",
        json={"text": "这个房间", "expected_turn": 0},
        headers={"Idempotency-Key": "history-reply-123"},
    ).json()
    history = task["agent_run"]["conversation"]
    assert [item["role"] for item in history] == ["user", "assistant", "user"]
    assert (
        history[1]["text"] == question["question"]
        and history[1]["options"][0]["label"] == before["rooms"][0]["name"]
    )
    assert any(
        message.type == "ai" and question["question"] in message.content
        for message in model.calls[1][0]
    )
    assert task["agent_run"]["timings"]["validation_ms"] >= 0
    assert task["agent_run"]["timings"]["execution_ms"] >= 0


def test_cancellation_releases_claim_and_preserves_issued_calls(client):
    import asyncio
    from types import SimpleNamespace

    from homemind.agent.schemas import AgentRequest
    from homemind.agent.service import create_agent
    from homemind.persistence.models import Task

    before = home(client)

    async def exercise():
        entered = asyncio.Event()

        async def block():
            entered.set()
            await asyncio.sleep(30)
            return AIMessage(content="{}")

        client.app.state.agent_model = ScriptedModel(block)
        request = SimpleNamespace(app=client.app, state=SimpleNamespace(home_id=before["home_id"]))
        job = asyncio.create_task(
            create_agent(
                request,
                AgentRequest(text="开灯", expected_world_id=before["world_id"]),
                "cancel-create-123",
            )
        )
        await asyncio.wait_for(entered.wait(), 2)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert before["home_id"] not in client.app.state.database.busy
        async with client.app.state.database.sessions() as session:
            from sqlalchemy import select

            task = await session.scalar(
                select(Task).where(Task.idempotency_key == "cancel-create-123")
            )
            assert task.status == "failed" and task.agent_run["failure_code"] == "request_cancelled"
            assert task.agent_run["model_calls"] == 1

    asyncio.run(exercise())


def test_usage_becomes_unknown_if_later_request_has_no_usage(client):
    reads = AIMessage(
        content="",
        tool_calls=[{"id": "read", "name": "read_home", "args": {}, "type": "tool_call"}],
        usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12},
    )
    model = ScriptedModel(reads, TimeoutError("private"))
    task = submit(client, model).json()
    assert task["agent_run"]["model_calls"] == 2 and task["agent_run"]["usage"] is None


def test_whole_home_batch_in_single_room_requires_confirmation(client):
    before = home(client)
    other_room = before["rooms"][1]["id"]
    for entity in before["entities"]:
        if entity["room_id"] == other_room:
            client.delete("/simulation/entities/" + entity["id"])
    assert client.delete("/simulation/rooms/" + other_room).status_code == 200
    before = home(client)
    result = cooling(before)
    task = submit(client, ScriptedModel(result)).json()
    assert task["status"] == "waiting_confirmation" and not task["actions"]


def test_debug_disabled_rule_time_gates_keep_available_paths(tmp_path):
    from conftest import authenticated_client

    with authenticated_client(tmp_path / "rules-plain.db", debug=False) as client:
        before = home(client)
        room = before["rooms"][0]
        for scenario in ("homecoming", "sleep"):
            response = client.post(
                "/tasks",
                json={"scenario": scenario, "room_ids": [room["id"]]},
                headers={"Idempotency-Key": "plain-rule-" + scenario},
            )
            assert (
                response.status_code == 422
                and response.json()["detail"]["code"] == "simulation_debug_required"
            )
            assert home(client) == before
        assert (
            client.post(
                "/tasks",
                json={"scenario": "away", "room_ids": [room["id"]]},
                headers={"Idempotency-Key": "plain-rule-away"},
            ).json()["status"]
            == "succeeded"
        )
        # Use the actual public temperature; this goal needs no clock.
        response = client.post(
            "/tasks",
            json={
                "scenario": "sleep",
                "room_ids": [room["id"]],
                "target_temperature_c": int(room["temperature_c"]),
            },
            headers={"Idempotency-Key": "plain-sleep-now"},
        )
        assert response.status_code == 200 and response.json()["status"] == "succeeded"


def test_parent_environment_cannot_enable_remote_tracing(client, monkeypatch):
    from contextlib import contextmanager

    from langsmith import tracing_context as real_context

    from homemind.agent import graph

    seen = []

    @contextmanager
    def disabled_context(**kwargs):
        seen.append(kwargs)
        with real_context(**kwargs):
            yield

    monkeypatch.setattr(graph, "tracing_context", disabled_context, raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    task = submit(client, ScriptedModel(plan(home(client)))).json()
    assert task["status"] == "succeeded" and seen == [{"enabled": False}]


@pytest.mark.parametrize(
    "kind,conflict",
    [("create", False), ("create", True), ("reply", False), ("reply", True), ("confirm", False)],
)
def test_idempotency_rechecked_after_waiting_for_claim(client, monkeypatch, kind, conflict):
    import asyncio
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    from homemind.agent.schemas import AgentRequest, ConfirmRequest, ReplyRequest
    from homemind.agent.service import confirm_agent, create_agent, reply_agent
    from homemind.simulation.models import SimulationError

    snapshot = home(client)
    question = {"kind": "clarify", "question": "哪个房间", "options": []}
    if kind == "reply":
        saved = submit(client, ScriptedModel(question)).json()
    elif kind == "confirm":
        saved = submit(client, ScriptedModel(plan(snapshot, "away", all_rooms=True))).json()
    else:
        saved = None
    model = ScriptedModel(plan(snapshot))
    client.app.state.agent_model = model
    database = client.app.state.database
    original = database.sessions
    request = SimpleNamespace(app=client.app, state=SimpleNamespace(home_id=snapshot["home_id"]))

    async def exercise():
        checked, release = asyncio.Event(), asyncio.Event()

        class PausedSessions:
            first = True

            def __call__(self):
                is_first = self.first
                self.first = False

                @asynccontextmanager
                async def manager():
                    async with original() as session:
                        yield session
                    if is_first:
                        checked.set()
                        await release.wait()

                return manager()

            def begin(self):
                return original.begin()

        monkeypatch.setattr(database, "sessions", PausedSessions())

        async def invoke(different=False):
            text = "另一个答案" if different else "原始答案"
            if kind == "create":
                return await create_agent(
                    request,
                    AgentRequest(text=text, expected_world_id=snapshot["world_id"]),
                    "racing-create-123",
                )
            if kind == "reply":
                return await reply_agent(
                    request,
                    saved["id"],
                    ReplyRequest(text=text, expected_turn=0),
                    "racing-reply-123",
                )
            return await confirm_agent(
                request, saved["id"], ConfirmRequest(expected_turn=0), "racing-confirm-123"
            )

        first = asyncio.create_task(invoke())
        try:
            await asyncio.wait_for(checked.wait(), 2)
            winner = await invoke(conflict)
            assert not database.busy
            release.set()
            if conflict:
                with pytest.raises(SimulationError) as caught:
                    await first
                assert caught.value.status == 409 and caught.value.code == "idempotency_conflict"
            else:
                assert await first == winner
            assert not database.busy
            assert len(model.calls) == (0 if kind == "confirm" else 1)
        finally:
            release.set()
            if not first.done():
                first.cancel()
                await asyncio.gather(first, return_exceptions=True)
            monkeypatch.setattr(database, "sessions", original)

    asyncio.run(exercise())


def test_actual_inflight_model_rejects_another_claim(client):
    import asyncio
    from types import SimpleNamespace

    from homemind.agent.schemas import AgentRequest
    from homemind.agent.service import create_agent
    from homemind.simulation.models import SimulationError

    snapshot = home(client)
    request = SimpleNamespace(app=client.app, state=SimpleNamespace(home_id=snapshot["home_id"]))
    body = AgentRequest(text="开灯", expected_world_id=snapshot["world_id"])

    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()

        async def block():
            entered.set()
            await release.wait()
            return AIMessage(content=json.dumps(plan(snapshot)))

        model = ScriptedModel(block)
        client.app.state.agent_model = model
        first = asyncio.create_task(create_agent(request, body, "actual-inflight-123"))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            with pytest.raises(SimulationError) as caught:
                await create_agent(request, body, "different-claim-123")
            assert caught.value.code == "home_busy" and caught.value.status == 409
            release.set()
            assert (await first)["status"] == "succeeded" and len(model.calls) == 1
        finally:
            release.set()
            if not first.done():
                first.cancel()
                await asyncio.gather(first, return_exceptions=True)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "output,status",
    [
        ({"kind": "clarify", "question": "哪个房间", "options": []}, "waiting_input"),
        ({"kind": "refuse", "reason": "能力不支持"}, "failed"),
    ],
)
def test_unexecuted_verification_has_stable_shape_and_no_fake_failure_time(client, output, status):
    task = submit(client, ScriptedModel(output)).json()
    assert task["status"] == status
    assert task["verification"] == {
        "due_at_minutes": None,
        "checked_at_minutes": 0,
        "conditions": [],
    }
    assert client.get("/tasks/" + task["id"]).json() == task
    assert client.post("/tasks/" + task["id"] + "/verify", json={}).json() == task
    assert all(
        "elapsed_ms" not in record
        for record in task["agent_run"]["records"]
        if record["stage"] == "failed"
    )


def test_contradictory_light_plan_blocks_all_actions_before_first_write(client):
    snapshot = home(client)
    room_id = snapshot["rooms"][0]["id"]
    response = client.post(
        "/simulation/entities", json={"room_id": room_id, "name": "参数矛盾测试灯", "type": "light"}
    )
    assert response.status_code == 200, response.text
    before = home(client)
    proposed = plan(before)
    assert len(proposed["actions"]) == 2
    proposed["actions"][1]["parameters"] = {"power": True, "brightness_pct": 0}
    task = submit(client, ScriptedModel(proposed), key="contradictory-light-123").json()
    assert task["status"] == "failed"
    assert task["agent_run"]["failure_code"] == "contradictory_parameters"
    assert task["actions"] == []
    assert home(client) == before


@pytest.mark.parametrize("brightness,power", [(0, False), (70, True)])
def test_agent_brightness_only_preserves_device_power_semantics(client, brightness, power):
    before = home(client)
    proposed = plan(before)
    light_id = proposed["actions"][0]["entity_id"]
    if brightness == 0:
        response = client.post(
            "/simulation/controls/" + light_id,
            json={"action": "set_light", "parameters": {"power": True}},
        )
        assert response.status_code == 200
    before = home(client)
    proposed = plan(before)
    proposed["actions"][0]["parameters"] = {"brightness_pct": brightness}
    task = submit(client, ScriptedModel(proposed), key="brightness-only-" + str(brightness)).json()
    assert task["status"] == "succeeded"
    assert task["actions"][0]["status"] == "verified"
    light = next(
        entity for entity in task["final_snapshot"]["entities"] if entity["id"] == light_id
    )
    assert light["state"]["brightness_pct"] == brightness and light["state"]["power"] is power
