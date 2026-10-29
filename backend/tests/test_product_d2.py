"""D2 uses injected models and real isolated Decimal simulation, never HTTP."""

import asyncio
from copy import deepcopy
from decimal import Decimal

import pytest
from test_m4_agent import ScriptedModel, home, plan, submit


def goal(snapshot, **extra):
    room_id = snapshot["rooms"][0]["id"]
    entities = {e["type"]: e for e in snapshot["entities"] if e["room_id"] == room_id}
    return (
        dict(
            kind="goal",
            room_id=room_id,
            climate_entity_id=entities["climate"]["id"],
            cover_entity_id=entities["cover"]["id"],
            target_temperature_c=26,
            ready_in_minutes=60,
            priority="energy_first",
            allowed_fan_modes=["low", "auto"],
            cover_constraint="allow_open_close",
            keep_entity_ids=[],
            protected_room_ids=[],
        )
        | extra
    )


def selected(snapshot, contract, candidate_id="c1", fan="low", cover=0):
    actions = [
        dict(
            entity_id=contract["climate_entity_id"],
            room_id=contract["room_id"],
            action="set_climate",
            parameters=dict(mode="cool", target_temperature_c=26, fan_mode=fan),
        )
    ]
    if contract["cover_entity_id"] and contract["cover_constraint"] != "keep":
        actions.append(
            dict(
                entity_id=contract["cover_entity_id"],
                room_id=contract["room_id"],
                action="set_cover",
                parameters={"position_pct": cover},
            )
        )
    return dict(
        kind="selection",
        candidate_id=candidate_id,
        plan=plan(
            snapshot,
            "homecoming",
            actions=actions,
            temperatures=[
                dict(room_id=contract["room_id"], target=contract["target_temperature_c"])
            ],
            ready_in_minutes=contract["ready_in_minutes"],
            keep_entity_ids=contract["keep_entity_ids"],
            protected_room_ids=contract["protected_room_ids"],
        ),
    )


def experimental(client, model, key="forecast-create-123", **extra):
    return submit(
        client,
        model,
        dict(
            text="60分钟内客厅26度，能耗优先，其他不动",
            expected_world_id=home(client)["world_id"],
            strategy="single_forecast",
        )
        | extra,
        key=key,
    )


def test_experimental_pipeline_requires_confirmation_and_preserves_standard_hash(client):
    before = home(client)
    contract = goal(before)
    model = ScriptedModel(contract, selected(before, contract))
    response = experimental(client, model)
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["status"] == "waiting_confirmation" and task["actions"] == []
    assert home(client) == before and task["mode"] == "single_agent"
    run = task["agent_run"]
    assert run["strategy"] == "single_forecast" and run["pipeline_version"] == "d2-forecast-v1"
    assert run["goal"] == contract and run["selected_candidate_id"] == "c1"
    # Open cover also meets the 60-minute goal and avoids the 0.05 Wh movement.
    # Preserve the planner's legal but energy-suboptimal original selection.
    assert run["preference_optimal"] is False and run["model_calls"] == 2
    assert run["forecast"]["energy_scope_entity_ids"] == [
        contract["climate_entity_id"],
        contract["cover_entity_id"],
    ]
    assert len(run["forecast"]["candidates"]) == 4
    assert experimental(client, model).json() == task
    assert len(model.calls) == 2
    assert "forecast" in str(model.calls[1][0]) and "60分钟内" in str(model.calls[1][0])
    confirmed = client.post(
        f"/tasks/{task['id']}/confirm",
        json={"expected_turn": 0},
        headers={"Idempotency-Key": "forecast-confirm-123"},
    ).json()
    assert confirmed["status"] == "waiting_verification" and len(confirmed["actions"]) == 2
    advanced = client.post(
        f"/tasks/{task['id']}/advance",
        json={"expected_world_id": before["world_id"], "expected_simulated_minutes": 0},
        headers={"Idempotency-Key": "forecast-advance-123"},
    )
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["status"] == "succeeded"
    old = submit(client, ScriptedModel(plan(home(client))), key="old-standard-123").json()
    assert "strategy" not in old["request"]
    replay = submit(
        client, ScriptedModel(), old["request"] | {"strategy": "standard"}, key="old-standard-123"
    )
    assert replay.json()["id"] == old["id"]


def test_forecast_matches_four_manual_replays_and_keeps_private_source():
    from homemind.agent.forecast import forecast_plan
    from homemind.simulation.models import ControlRequest
    from homemind.simulation.physics import energy_wh
    from homemind.simulation.service import SimulationService

    engine = SimulationService()
    before = engine.snapshot()
    private_before = deepcopy(engine._rooms), deepcopy(engine._entities), deepcopy(engine._events)
    contract = goal(before)
    result = forecast_plan(engine, contract)
    assert engine.snapshot() == before
    assert (engine._rooms, engine._entities, engine._events) == private_before
    assert result["source"] == {
        k: before[k] for k in ("world_id", "revision", "config_revision", "simulated_minutes")
    }
    assert result["model_version"] == before["model_version"]
    for candidate in result["candidates"]:
        replay = SimulationService()
        replay._rooms, replay._entities = deepcopy(engine._rooms), deepcopy(engine._entities)
        scope = result["energy_scope_entity_ids"]
        baseline = sum((replay._entities[i].energy_watt_minutes for i in scope), Decimal(0))
        for action in candidate["actions"]:
            replay.control(
                action["entity_id"],
                ControlRequest(action=action["action"], parameters=action["parameters"]),
            )
        first = None
        for minute in range(1, 61):
            snapshot = replay.advance(1)
            temperature = next(r for r in snapshot["rooms"] if r["id"] == contract["room_id"])[
                "temperature_c"
            ]
            if temperature <= 26 and first is None:
                first = minute
        assert candidate["end_temperature_c"] == temperature
        assert candidate["first_observed_goal_minute"] == first
        assert candidate["energy_wh"] == energy_wh(
            sum((replay._entities[i].energy_watt_minutes for i in scope), Decimal(0)) - baseline
        )
    closed = [c for c in result["candidates"] if c["cover_position_pct"] == 0]
    assert [c["energy_wh"] for c in closed] == [550.05, 850.05]
    assert [c["first_observed_goal_minute"] for c in closed] == [41, 17]
    short = forecast_plan(engine, contract | {"ready_in_minutes": 20})
    assert [
        c["end_temperature_c"] for c in short["candidates"] if c["cover_position_pct"] == 0
    ] == [26.8, 26.0]


@pytest.mark.parametrize("mutation", ["goal", "extra_action", "keep", "missing_id", "wrong_action"])
def test_bad_selection_has_no_writes_or_invalid_candidate_id(client, mutation):
    before = home(client)
    contract = goal(before)
    output = selected(before, contract)
    extra = {}
    if mutation == "goal":
        output["plan"]["ready_in_minutes"] = 61
    elif mutation == "extra_action":
        output["plan"]["actions"] += plan(before)["actions"]
    elif mutation == "keep":
        extra["keep_entity_ids"] = [plan(before)["actions"][0]["entity_id"]]
    elif mutation == "missing_id":
        output["candidate_id"] = "PRIVATE-INVALID-ID"
    else:
        output["plan"]["actions"][0]["parameters"]["fan_mode"] = "auto"
    response = experimental(client, ScriptedModel(contract, output), **extra)
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["status"] == "failed" and task["actions"] == [] and home(client) == before
    assert "PRIVATE-INVALID-ID" not in str(task)


def test_no_deadline_candidate_clarifies_same_task_without_planner(client):
    before = home(client)
    contract = goal(before, ready_in_minutes=1)
    model = ScriptedModel(contract, goal(before), selected(before, goal(before)))
    task = experimental(client, model).json()
    assert task["status"] == "waiting_input" and task["agent_run"]["model_calls"] == 1
    assert task["agent_run"]["forecast"] and task["actions"] == [] and home(client) == before
    next_task = client.post(
        f"/tasks/{task['id']}/reply",
        json={"text": "改为60分钟", "expected_turn": 0},
        headers={"Idempotency-Key": "forecast-reply-123"},
    ).json()
    assert next_task["id"] == task["id"] and next_task["status"] == "waiting_confirmation"


def test_strategy_config_and_debug_gate(client, tmp_path):
    from conftest import authenticated_client

    assert client.get("/tasks/agent/config").json()["strategies"] == [
        "standard",
        "single_forecast",
        "expert_forecast",
    ]
    with authenticated_client(tmp_path / "plain-d2.db", debug=False) as plain:
        assert plain.get("/tasks/agent/config").json()["strategies"] == ["standard"]
        response = experimental(plain, ScriptedModel())
        assert response.status_code == 422
    assert experimental(client, ScriptedModel(), strategy="unknown_strategy").status_code == 422


def test_exact_clone_pending_archives_and_independent_lock():
    from homemind.agent.forecast import clone_engine
    from homemind.simulation.models import ControlRequest, FaultRequest
    from homemind.simulation.service import SimulationService

    engine = SimulationService()
    contract = goal(engine.snapshot())
    engine._rooms[contract["room_id"]].temperature = Decimal("28.049")
    climate = engine._entities[contract["climate_entity_id"]]
    climate.energy_watt_minutes = Decimal("1.00049")
    engine.set_fault(climate.id, FaultRequest(mode="delayed"))
    engine.control(climate.id, ControlRequest(action="set_climate", parameters={"mode": "cool"}))
    light = next(e for e in engine._entities.values() if e.type == "light")
    engine.delete_entity(light.id)
    clone = clone_engine(engine)
    assert clone._lock is not engine._lock
    assert clone._rooms == engine._rooms and clone._entities == engine._entities
    assert clone._archives == engine._archives and clone._events == engine._events
    assert clone._new_events == engine._new_events
    assert clone._rooms[contract["room_id"]].temperature == Decimal("28.049")
    assert clone._entities[climate.id].energy_watt_minutes == Decimal("1.00049")
    clone.advance(2)
    assert climate.pending is not None and engine._minutes == 0


def test_initial_goal_zero_half_cover_keep_scope_and_hidden_other_room():
    from homemind.agent.forecast import forecast_plan
    from homemind.simulation.models import ControlRequest, EventRequest
    from homemind.simulation.service import SimulationService

    engine = SimulationService()
    contract = goal(engine.snapshot(), cover_constraint="keep")
    cover_id = contract["cover_entity_id"]
    contract["keep_entity_ids"] = [cover_id]
    engine.control(cover_id, ControlRequest(action="set_cover", parameters={"position_pct": 50}))
    sensor_id = engine._rooms[contract["room_id"]].primary_temperature_entity_id
    engine.event(EventRequest(entity_id=sensor_id, temperature_c=26.0))
    other = next(
        e
        for e in engine._entities.values()
        if e.room_id != contract["room_id"] and e.type == "temperature"
    )
    engine.event(EventRequest(entity_id=other.id, known=False))
    baseline = engine.snapshot()
    result = forecast_plan(engine, contract)
    assert len(result["candidates"]) == 2
    assert all(
        c["first_observed_goal_minute"] == 0 and c["cover_position_pct"] == 50
        for c in result["candidates"]
    )
    assert all(len(c["actions"]) == 1 for c in result["candidates"])
    assert other.id not in str(result)
    assert engine.snapshot() == baseline


@pytest.mark.parametrize(
    "defect",
    [
        "missing_window",
        "missing_occupancy",
        "unknown_secondary_occupancy",
        "unknown_secondary_window",
        "fault",
        "pending",
        "two_climates",
        "two_covers",
        "too_many_entities",
        "too_many_rooms",
        "too_many_archives",
    ],
)
def test_unsafe_forecast_inputs_fail_closed(defect):
    from homemind.agent.forecast import forecast_plan
    from homemind.simulation.models import EntityCreate, FaultMode, PendingControl, SimulationError
    from homemind.simulation.service import SimulationService

    engine = SimulationService()
    contract = goal(engine.snapshot())
    room = engine._rooms[contract["room_id"]]
    if defect.startswith("missing_"):
        kind = defect.removeprefix("missing_")
        for e in engine._entities.values():
            if e.room_id == room.id and e.type == kind:
                e.enabled = False
    elif defect.startswith("unknown_secondary_"):
        kind = defect.removeprefix("unknown_secondary_")
        engine.create_entity(EntityCreate(room_id=room.id, name="secondary", type=kind))
        next(reversed(engine._entities.values())).known = False
    elif defect == "fault":
        engine._entities[contract["cover_entity_id"]].fault_mode = FaultMode.NO_EFFECT
    elif defect == "pending":
        engine._entities[contract["climate_entity_id"]].pending = PendingControl(2, {"mode": "off"})
    elif defect.startswith("two_"):
        kind = "climate" if defect == "two_climates" else "cover"
        engine.create_entity(EntityCreate(room_id=room.id, name="additional", type=kind))
    elif defect == "too_many_entities":
        for i in range(257):
            engine._entities[f"archive-{i}"] = deepcopy(next(iter(engine._entities.values())))
            engine._entities[f"archive-{i}"].archived = True
    elif defect == "too_many_rooms":
        for i in range(17):
            engine._rooms[f"room-{i}"] = deepcopy(room)
    else:
        engine._archives = [
            dict(entity=deepcopy(next(iter(engine._entities.values())))) for _ in range(257)
        ]
    before = engine.snapshot()
    with pytest.raises(SimulationError) as error:
        forecast_plan(engine, contract)
    assert error.value.code == "forecast_unavailable" and engine.snapshot() == before


def test_prediction_energy_uses_exact_increment_not_subtracted_rounded_totals():
    from homemind.agent.forecast import forecast_plan
    from homemind.simulation.service import SimulationService

    engine = SimulationService()
    contract = goal(engine.snapshot(), ready_in_minutes=1)
    for e in engine._entities.values():
        e.energy_watt_minutes = Decimal("0.0299")
    result = forecast_plan(engine, contract)
    assert result["candidates"][0]["energy_wh"] == 9.217


def test_forecast_worker_cancel_holds_slot_until_worker_really_exits(monkeypatch):
    import threading
    import time

    from homemind.agent import forecast
    from homemind.simulation.models import SimulationError

    entered, release = threading.Event(), threading.Event()
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(forecast, "_slots", slots)
    seen_cancel = []

    def blocked(*args, cancel, **kwargs):
        entered.set()
        release.wait(2)
        seen_cancel.append(cancel.is_set())
        return {}

    monkeypatch.setattr(forecast, "forecast_plan", blocked)

    async def exercise():
        task = asyncio.create_task(forecast.run_forecast(None, {}, time.monotonic() + 5))
        try:
            while not entered.is_set():
                await asyncio.sleep(0.001)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(SimulationError):
                await forecast.run_forecast(None, {}, time.monotonic() + 5)
            assert not slots.acquire(blocking=False)
        finally:
            release.set()
        while not seen_cancel:
            await asyncio.sleep(0.001)
        assert seen_cancel == [True] and slots.acquire(blocking=False)
        slots.release()

    asyncio.run(exercise())


def test_forecast_checks_cpu_cancellation_and_deadline():
    import threading
    import time

    from homemind.agent.forecast import forecast_plan
    from homemind.simulation.models import SimulationError
    from homemind.simulation.service import SimulationService

    engine = SimulationService()
    contract = goal(engine.snapshot(), ready_in_minutes=1440)
    stop = threading.Event()
    stop.set()
    before = engine.snapshot()
    with pytest.raises(SimulationError, match="取消"):
        forecast_plan(engine, contract, cancel=stop)
    with pytest.raises(SimulationError) as error:
        forecast_plan(engine, contract, deadline=time.monotonic() - 1)
    assert error.value.code == "round_timeout" and engine.snapshot() == before


def test_confirm_rechecks_versions_and_never_executes_stale_forecast(client):
    before = home(client)
    contract = goal(before)
    task = experimental(client, ScriptedModel(contract, selected(before, contract))).json()
    client.post("/simulation/advance", json={"minutes": 1})
    changed = home(client)
    confirmed = client.post(
        f"/tasks/{task['id']}/confirm",
        json={"expected_turn": 0},
        headers={"Idempotency-Key": "d2-stale-confirm-123"},
    ).json()
    assert confirmed["status"] == "failed" and confirmed["actions"] == []
    assert confirmed["agent_run"]["failure_code"] == "state_changed" and home(client) == changed


def test_experimental_creation_key_conflicts_with_standard(client):
    before = home(client)
    task = submit(
        client,
        ScriptedModel(plan(before)),
        body=dict(text="same", expected_world_id=before["world_id"]),
    ).json()
    response = submit(
        client, ScriptedModel(), body=task["request"] | {"strategy": "single_forecast"}
    )
    assert response.status_code == 409


def test_experimental_round_task_budgets_and_unknown_usage(client):
    from langchain_core.messages import AIMessage

    before = home(client)
    contract = goal(before)
    read = AIMessage(
        content="",
        tool_calls=[dict(id="read", name="read_home", args={}, type="tool_call")],
        usage_metadata=dict(input_tokens=10, output_tokens=2, total_tokens=12),
    )
    # Goal + 5 issued planner requests per round; final planner read cannot trigger a sixth.
    model = ScriptedModel(contract, read, read, read, read, read)
    task = experimental(client, model).json()
    assert task["status"] == "failed" and task["agent_run"]["model_calls"] == 6
    assert (
        task["agent_run"]["failure_code"] == "model_budget" and task["agent_run"]["usage"] is None
    )
    assert task["actions"] == [] and home(client) == before


def test_experimental_cumulative_budget_stops_before_thirteenth_request(client):
    from langchain_core.messages import AIMessage

    before = home(client)
    contract = goal(before)
    read = AIMessage(
        content="", tool_calls=[dict(id="r", name="read_home", args={}, type="tool_call")]
    )
    question = dict(kind="clarify", question="Please specify preference", options=[])
    model = ScriptedModel(
        contract, read, read, read, read, question, contract, read, read, read, read, question
    )
    task = experimental(client, model).json()
    assert task["status"] == "waiting_input" and task["agent_run"]["model_calls"] == 6
    task = client.post(
        f"/tasks/{task['id']}/reply",
        json=dict(text="energy first", expected_turn=0),
        headers={"Idempotency-Key": "d2-budget-reply-1"},
    ).json()
    assert task["status"] == "waiting_input" and task["agent_run"]["model_calls"] == 12
    task = client.post(
        f"/tasks/{task['id']}/reply",
        json=dict(text="energy first", expected_turn=1),
        headers={"Idempotency-Key": "d2-budget-reply-2"},
    ).json()
    assert task["status"] == "failed" and task["agent_run"]["model_calls"] == 12
    assert task["agent_run"]["failure_code"] == "task_model_budget" and len(model.calls) == 12
    assert task["agent_run"]["goal"] is None and task["agent_run"]["forecast"] is None


@pytest.mark.parametrize("phase", ["goal", "planner"])
def test_experimental_timeout_accounts_for_actual_issued_calls(client, monkeypatch, phase):
    from homemind.agent import graph

    monkeypatch.setattr(graph, "MODEL_TIMEOUT_SECONDS", 0.02)

    async def block():
        await asyncio.sleep(1)

    before = home(client)
    model = ScriptedModel(block) if phase == "goal" else ScriptedModel(goal(before), block)
    task = experimental(client, model).json()
    assert task["status"] == "failed" and task["actions"] == [] and home(client) == before
    assert task["agent_run"]["model_calls"] == (1 if phase == "goal" else 2)
    assert (
        task["agent_run"]["usage"] is None and task["agent_run"]["failure_code"] == "model_timeout"
    )


@pytest.mark.parametrize("phase", ["goal", "planner"])
def test_experimental_cancellation_saves_issued_accounting_and_releases_home(client, phase):
    from types import SimpleNamespace

    from sqlalchemy import select

    from homemind.agent.schemas import AgentRequest
    from homemind.agent.service import create_agent
    from homemind.persistence.models import Task

    before = home(client)

    async def exercise():
        entered = asyncio.Event()

        async def block():
            entered.set()
            await asyncio.sleep(30)

        model = ScriptedModel(block) if phase == "goal" else ScriptedModel(goal(before), block)
        client.app.state.agent_model = model
        request = SimpleNamespace(app=client.app, state=SimpleNamespace(home_id=before["home_id"]))
        task = asyncio.create_task(
            create_agent(
                request,
                AgentRequest(
                    text="test", expected_world_id=before["world_id"], strategy="single_forecast"
                ),
                "d2-cancel-123",
            )
        )
        await asyncio.wait_for(entered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not client.app.state.database.busy
        async with client.app.state.database.sessions() as session:
            saved = await session.scalar(
                select(Task).where(Task.idempotency_key == "d2-cancel-123")
            )
            assert (
                saved.status == "failed" and saved.agent_run["failure_code"] == "request_cancelled"
            )
            assert saved.agent_run["model_calls"] == (1 if phase == "goal" else 2)
            assert saved.agent_run["usage"] is None

    asyncio.run(exercise())
    assert home(client) == before


def test_experimental_first_goal_cannot_guess_ambiguous_literal_room(client):
    snapshot = home(client)
    client.patch("/simulation/rooms/" + snapshot["rooms"][1]["id"], json={"name": "客厅"})
    snapshot = home(client)
    model = ScriptedModel(goal(snapshot), selected(snapshot, goal(snapshot)))
    task = experimental(client, model).json()
    assert task["status"] == "waiting_input" and task["agent_run"]["model_calls"] == 1
    assert len(task["agent_run"]["options"]) == 2 and task["agent_run"]["goal"] is None
    assert task["actions"] == [] and home(client) == snapshot


def test_forecast_internal_failure_is_public_zero_write_and_releases_claim(client, monkeypatch):
    from homemind.agent import forecast

    def broken(*_args, **_kwargs):
        raise RuntimeError("PRIVATE-INTERNAL-FORECAST-STATE")

    monkeypatch.setattr(forecast, "forecast_plan", broken)
    before = home(client)
    response = experimental(client, ScriptedModel(goal(before)))
    assert response.status_code == 200
    task = response.json()
    assert (
        task["status"] == "failed" and task["agent_run"]["failure_code"] == "forecast_unavailable"
    )
    assert task["agent_run"]["model_calls"] == 1 and not task["actions"]
    assert "PRIVATE-INTERNAL" not in str(task) and home(client) == before
    assert not client.app.state.database.busy


def test_confirmation_rejects_changed_forecast_model_version(client):
    from sqlalchemy import select

    from homemind.persistence.models import Task

    before = home(client)
    contract = goal(before)
    task = experimental(client, ScriptedModel(contract, selected(before, contract))).json()

    async def corrupt_version():
        async with client.app.state.database.sessions.begin() as session:
            stored = await session.scalar(select(Task).where(Task.id == task["id"]))
            run = deepcopy(stored.agent_run)
            run["forecast"]["model_version"] = "outdated-physics"
            stored.agent_run = run

    asyncio.run(corrupt_version())
    response = client.post(
        f"/tasks/{task['id']}/confirm",
        json={"expected_turn": 0},
        headers={"Idempotency-Key": "d2-model-version-confirm"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed" and response.json()["actions"] == []
    assert home(client) == before


def test_running_real_forecast_cpu_observes_cancel_and_returns_worker_slot(monkeypatch):
    import threading
    import time

    from homemind.agent import forecast
    from homemind.simulation.service import SimulationService

    engine = SimulationService()
    contract = goal(engine.snapshot(), ready_in_minutes=1440)
    before = engine.snapshot()
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(forecast, "_slots", slots)
    entered = threading.Event()
    calls = []
    advance = SimulationService.advance

    def observed_advance(self, minutes):
        calls.append(minutes)
        entered.set()
        return advance(self, minutes)

    monkeypatch.setattr(SimulationService, "advance", observed_advance)

    async def exercise():
        task = asyncio.create_task(forecast.run_forecast(engine, contract, time.monotonic() + 10))
        while not entered.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        deadline = time.monotonic() + 1
        while not slots.acquire(blocking=False):
            assert time.monotonic() < deadline
            await asyncio.sleep(0.001)
        slots.release()

    asyncio.run(exercise())
    assert 0 < len(calls) < 5760 and engine.snapshot() == before


def test_experimental_planning_never_invokes_physical_database_save(client, monkeypatch):
    from homemind.persistence import database

    async def forbidden_save(*_args, **_kwargs):
        raise AssertionError("Forecast may persist task metadata, never physical engine records")

    monkeypatch.setattr(database, "save_engine", forbidden_save)
    before = home(client)
    contract = goal(before)
    task = experimental(client, ScriptedModel(contract, selected(before, contract))).json()
    assert task["status"] == "waiting_confirmation" and home(client) == before


def test_final_plan_failure_does_not_publish_unbound_selection(client):
    before = home(client)
    light = next(e for e in before["entities"] if e["type"] == "light")
    response = client.patch("/simulation/entities/" + light["id"], json={"enabled": False})
    assert response.status_code == 200
    before = home(client)
    contract = goal(before, keep_entity_ids=[light["id"]])
    result = experimental(
        client, ScriptedModel(contract, selected(before, contract)), keep_entity_ids=[light["id"]]
    ).json()
    assert result["status"] == "failed" and result["actions"] == []
    assert result["agent_run"]["failure_code"] == "disabled_reference"
    assert result["agent_run"]["proposed_plan"] is None
    assert result["agent_run"]["selected_candidate_id"] is None
    assert result["agent_run"]["preference_optimal"] is None
    assert home(client) == before
