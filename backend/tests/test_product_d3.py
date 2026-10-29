"""D3 actual graphs with controlled SDK responses; external HTTP remains blocked."""

import asyncio
import json
from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage
from test_m4_agent import ScriptedModel, home, submit
from test_product_d2 import goal, selected

ROLES = ["coordinator_goal", "comfort", "energy", "coordinator_plan"]


def advice(role, candidate="c1", **extra):
    return (
        dict(
            role=role,
            outcome="recommend",
            preferred_candidate_id=candidate,
            evidence_refs=["goal", "candidate:" + candidate],
            public_summary="根据本轮预测提出公开建议",
        )
        | extra
    )


def context(messages):
    prompt = messages[0].content
    marker = "Frozen public context: "
    return json.JSONDecoder().raw_decode(prompt.split(marker, 1)[1])[0] if marker in prompt else {}


class ExpertModel:
    def __init__(self, snapshot, **outputs):
        self.snapshot = snapshot
        self.outputs = outputs
        self.calls = []

    async def ainvoke(self, messages, tools):
        facts = context(messages)
        role = facts.get("role", "goal" if "forecast" not in facts else "coordinator")
        self.calls.append((role, messages, tools, facts))
        output = self.outputs.get(role)
        if output is None:
            output = (
                goal(self.snapshot)
                if role == "goal"
                else advice(role)
                if role in {"comfort", "energy"}
                else selected(self.snapshot, goal(self.snapshot))
            )
        if callable(output):
            output = await output()
        if isinstance(output, Exception):
            raise output
        return output if isinstance(output, AIMessage) else AIMessage(content=json.dumps(output))


def expert(client, model, key="expert-create-123", **extra):
    return submit(
        client,
        model,
        dict(
            text="60分钟内客厅26度，能耗优先，其他不动",
            expected_world_id=home(client)["world_id"],
            strategy="expert_forecast",
        )
        | extra,
        key=key,
    )


def test_expert_request_enters_actual_multi_agent_pipeline(client):
    before = home(client)
    response = expert(client, ExpertModel(before))
    assert response.status_code == 200, response.text
    task = response.json()
    assert task["mode"] == "multi_agent" and task["status"] == "waiting_confirmation"
    assert task["agent_run"]["pipeline_version"] == "d3-experts-v1"
    assert [r["role"] for r in task["agent_run"]["role_runs"]] == ROLES
    assert task["actions"] == [] and home(client) == before


def test_multi_agent_zero_action_verify_never_creates_success(client):
    from sqlalchemy import select

    from homemind.persistence.models import Task

    task = submit(client, ScriptedModel(dict(kind="refuse", reason="不支持"))).json()

    async def make_multi():
        async with client.app.state.database.sessions.begin() as session:
            stored = await session.scalar(select(Task).where(Task.id == task["id"]))
            stored.mode = "multi_agent"

    asyncio.run(make_multi())
    result = client.post(f"/tasks/{task['id']}/verify", json={}).json()
    assert result["status"] == "failed" and result["actions"] == []


def test_experts_enter_async_event_barrier_before_either_can_finish():
    from homemind.agent.pipeline import run_pipeline
    from homemind.simulation.service import SimulationService

    async def exercise():
        engine = SimulationService()
        before = engine.snapshot()
        entered = {role: asyncio.Event() for role in ("comfort", "energy")}

        async def branch(role, peer):
            entered[role].set()
            await entered[peer].wait()
            return advice(role)

        model = ExpertModel(
            before,
            comfort=lambda: branch("comfort", "energy"),
            energy=lambda: branch("energy", "comfort"),
        )
        result = await asyncio.wait_for(
            run_pipeline(
                model,
                before,
                {},
                [{"role": "user", "text": "能耗优先，60分钟客厅26度"}],
                engine,
                {
                    "text": "能耗优先，60分钟客厅26度",
                    "strategy": "expert_forecast",
                    "keep_entity_ids": [],
                    "protected_room_ids": [],
                },
                0,
            ),
            3,
        )
        assert all(event.is_set() for event in entered.values()), "Both expert nodes must run"
        assert result["output"]["kind"] == "selection" and result["model_calls"] == 4
        assert engine.snapshot() == before

    asyncio.run(exercise())


def message(output, tokens=10):
    return AIMessage(
        content=json.dumps(output),
        usage_metadata=dict(input_tokens=tokens, output_tokens=2, total_tokens=tokens + 2),
        response_metadata={"model_name": "controlled-experts", "PRIVATE-PROVIDER": "SECRET"},
    )


def read_message():
    return AIMessage(
        content="",
        tool_calls=[dict(id="r", name="read_home", args={}, type="tool_call")],
        usage_metadata=dict(input_tokens=3, output_tokens=1, total_tokens=4),
    )


def test_public_ledger_facts_disagreement_and_confirm_replay(client, monkeypatch):
    from homemind.agent import service
    from homemind.persistence import database

    before = home(client)
    contract = goal(before)
    model = ExpertModel(
        before,
        goal=message(contract),
        comfort=message(advice("comfort", "c3")),
        energy=message(advice("energy", "c2")),
        coordinator=message(selected(before, contract)),
    )
    saves = []
    save_engine = database.save_engine

    async def observe_save(*args, **kwargs):
        saves.append(True)
        return await save_engine(*args, **kwargs)

    monkeypatch.setattr(database, "save_engine", observe_save)
    monkeypatch.setattr(service, "save_engine", observe_save)
    task = expert(client, model).json()
    run = task["agent_run"]
    assert task["status"] == "waiting_confirmation", task
    assert run["strategy"] == "expert_forecast" and run["selected_candidate_id"] == "c1"
    assert run["preference_optimal"] is False  # Legal suboptimal model choice is preserved.
    assert run["model_calls"] == 4 and run["usage"] == dict(input_tokens=40, output_tokens=8)
    expected = {
        "role",
        "status",
        "model_calls",
        "tool_calls",
        "usage",
        "actual_model",
        "elapsed_ms",
        "failure_code",
        "advice",
    }
    for role in run["role_runs"]:
        assert set(role) == expected
        assert role["status"] == "succeeded" and role["model_calls"] == 1
        assert role["actual_model"] == "controlled-experts" and role["tool_calls"] == 0
        assert role["elapsed_ms"] >= 0 and role["failure_code"] is None
    assert len(run["rounds"][0]["roles"]) == 4
    assert all("advice" not in role for role in run["rounds"][0]["roles"])
    assert "SECRET" not in str(task) and "PRIVATE-PROVIDER" not in str(task)
    facts = {role: data for role, _messages, _tools, data in model.calls}
    for role in ("comfort", "energy"):
        assert facts[role]["home"] == before and facts[role]["goal"] == contract
        assert len(facts[role]["forecast"]["candidates"]) == 4
        assert "advice" not in facts[role]
        sent = next(call for call in model.calls if call[0] == role)
        assert sent[2] == [] and "60分钟内客厅26度" in str(sent[1])
    assert [a["role"] for a in facts["coordinator"]["advice"]] == ["comfort", "energy"]
    assert "Integrate the two expert Advice" in model.calls[-1][1][0].content
    assert "Plan.rationale" in model.calls[-1][1][0].content
    assert "Never claim consensus" in model.calls[-1][1][0].content
    assert home(client) == before and saves == []
    assert expert(client, model).json() == task and len(model.calls) == 4
    for strategy in ("standard", "single_forecast"):
        assert expert(client, model, strategy=strategy).status_code == 409
    url = f"/tasks/{task['id']}"
    confirmed = client.post(
        url + "/confirm",
        json={"expected_turn": 0},
        headers={"Idempotency-Key": "expert-confirm-123"},
    ).json()
    assert confirmed["status"] == "waiting_verification" and len(confirmed["actions"]) == 2
    assert len(saves) == 1
    assert (
        client.post(
            url + "/confirm",
            json={"expected_turn": 0},
            headers={"Idempotency-Key": "expert-confirm-123"},
        ).json()
        == confirmed
    )
    assert len(saves) == 1
    advanced = client.post(
        url + "/advance",
        json={"expected_world_id": before["world_id"], "expected_simulated_minutes": 0},
        headers={"Idempotency-Key": "expert-advance-123"},
    ).json()
    assert advanced["status"] == "succeeded"
    assert [r["status"] for r in advanced["agent_run"]["role_runs"]] == ["succeeded"] * 4


@pytest.mark.parametrize("role", ["comfort", "energy"])
@pytest.mark.parametrize("outcome", ["clarify", "refuse"])
def test_expert_clarify_or_refuse_stops_coordinator_and_can_reply(client, role, outcome):
    before = home(client)
    output = advice(
        role,
        outcome=outcome,
        preferred_candidate_id=None,
        evidence_refs=["goal"],
        public_summary="请明确是否允许修改期限？",
    )
    model = ExpertModel(before, **{role: output})
    task = expert(client, model).json()
    assert task["status"] == ("waiting_input" if outcome == "clarify" else "failed")
    assert task["actions"] == [] and home(client) == before and len(model.calls) == 3
    assert task["agent_run"]["role_runs"][3]["status"] == "skipped"
    if outcome == "refuse":
        assert task["agent_run"]["failure_code"] == "refused"
        return
    assert task["agent_run"]["options"] == []
    model.outputs.clear()
    response = client.post(
        f"/tasks/{task['id']}/reply",
        json={"text": "期限仍60分钟，能耗优先", "expected_turn": 0},
        headers={"Idempotency-Key": "expert-reply-123"},
    )
    assert response.status_code == 200, response.text
    replied = response.json()
    assert replied["id"] == task["id"] and replied["status"] == "waiting_confirmation"
    assert replied["agent_run"]["model_calls"] == 7
    assert [r["model_calls"] for r in replied["agent_run"]["rounds"]] == [3, 4]
    assert all(
        "advice" not in r for round_ in replied["agent_run"]["rounds"] for r in round_["roles"]
    )
    assert "期限仍60分钟" in str(model.calls[-2][1])
    assert (
        client.post(
            f"/tasks/{task['id']}/reply",
            json={"text": "期限仍60分钟，能耗优先", "expected_turn": 0},
            headers={"Idempotency-Key": "expert-reply-123"},
        ).json()
        == replied
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "extra",
        "role",
        "foreign_evidence",
        "duplicate",
        "missing_own",
        "unknown_candidate",
        "missing_candidate",
        "too_many_refs",
        "long_summary",
        "tool",
    ],
)
def test_invalid_expert_output_stops_whole_round_and_sanitizes(client, mutation):
    before = home(client)
    output = advice("comfort")
    if mutation == "extra":
        output["PRIVATE-PROVIDER"] = "SECRET"
    elif mutation == "role":
        output["role"] = "energy"
    elif mutation == "foreign_evidence":
        output["evidence_refs"].append("candidate:PRIVATE-INVALID-ID")
    elif mutation == "duplicate":
        output["evidence_refs"].append("goal")
    elif mutation == "missing_own":
        output["evidence_refs"] = ["goal"]
    elif mutation == "unknown_candidate":
        output["preferred_candidate_id"] = "PRIVATE-INVALID-ID"
    elif mutation == "missing_candidate":
        output["preferred_candidate_id"] = None
    elif mutation == "too_many_refs":
        output["evidence_refs"] = ["goal"] * 6
    elif mutation == "long_summary":
        output["public_summary"] = "x" * 1001
    else:
        output = read_message()
    task = expert(client, ExpertModel(before, comfort=output)).json()
    assert task["status"] == "failed" and task["actions"] == [] and home(client) == before
    run = task["agent_run"]
    assert run["failure_code"] == "analysis_incomplete" and run["model_calls"] == 3
    failed = run["role_runs"][1]
    assert failed["status"] == "failed" and failed["advice"] is None and failed["model_calls"] == 1
    assert (
        run["role_runs"][2]["status"] == "succeeded" and run["role_runs"][3]["status"] == "skipped"
    )
    assert "PRIVATE-INVALID-ID" not in str(task) and "SECRET" not in str(task)
    assert client.post(f"/tasks/{task['id']}/verify", json={}).json()["status"] == "failed"


def test_recommendation_must_be_deadline_feasible(client):
    before = home(client)
    task = expert(client, ExpertModel(before, goal=goal(before, ready_in_minutes=20))).json()
    assert task["status"] == "failed" and task["agent_run"]["failure_code"] == "analysis_incomplete"
    assert task["agent_run"]["role_runs"][1]["failure_code"] == "invalid_advice"
    assert task["actions"] == [] and home(client) == before


@pytest.mark.parametrize("first", ["comfort", "energy"])
def test_opposite_completion_orders_keep_fixed_advice_and_role_order(client, first):
    before = home(client)
    completed = []
    event = None

    async def output(role):
        nonlocal event
        if event is None:
            event = asyncio.Event()
        if role != first:
            await event.wait()
        completed.append(role)
        if role == first:
            event.set()
        return advice(role, "c3" if role == "comfort" else "c2")

    model = ExpertModel(before, comfort=lambda: output("comfort"), energy=lambda: output("energy"))
    task = expert(client, model).json()
    assert completed == [first, "energy" if first == "comfort" else "comfort"]
    assert (
        task["status"] == "waiting_confirmation"
        and [r["role"] for r in task["agent_run"]["role_runs"]] == ROLES
    )
    assert [a["role"] for a in model.calls[-1][3]["advice"]] == ["comfort", "energy"]


def test_model_timeout_keeps_peer_accounting_and_unknown_usage(client, monkeypatch):
    from homemind.agent import graph

    monkeypatch.setattr(graph, "MODEL_TIMEOUT_SECONDS", 0.03)

    async def blocked():
        await asyncio.Event().wait()

    before = home(client)
    model = ExpertModel(
        before, goal=message(goal(before)), comfort=blocked, energy=message(advice("energy"))
    )
    task = expert(client, model).json()
    run = task["agent_run"]
    assert task["status"] == "failed" and task["actions"] == [] and home(client) == before
    assert (
        run["failure_code"] == "analysis_incomplete"
        and run["model_calls"] == 3
        and run["usage"] is None
    )
    assert (
        run["role_runs"][1]["failure_code"] == "model_timeout"
        and run["role_runs"][1]["usage"] is None
    )
    assert run["role_runs"][2]["usage"] == dict(input_tokens=10, output_tokens=2)
    assert run["role_runs"][3]["status"] == "skipped"


@pytest.mark.parametrize("completed_peer", [False, True])
def test_cancellation_waits_for_all_parallel_role_accounting(client, completed_peer, monkeypatch):
    from types import SimpleNamespace

    from sqlalchemy import select

    from homemind.agent import pipeline
    from homemind.agent.schemas import AgentRequest
    from homemind.agent.service import create_agent
    from homemind.persistence.models import Task

    before = home(client)

    async def exercise():
        entered = {role: asyncio.Event() for role in ("comfort", "energy")}
        peer_settled = asyncio.Event()
        finished = []

        planner = pipeline.run_planner

        async def observed_planner(*args, **kwargs):
            result = await planner(*args, **kwargs)
            if kwargs.get("public_context", {}).get("role") == "energy":
                peer_settled.set()
            return result

        monkeypatch.setattr(pipeline, "run_planner", observed_planner)

        async def output(role):
            entered[role].set()
            if completed_peer and role == "energy":
                return message(advice(role))
            try:
                await asyncio.Event().wait()
            finally:
                finished.append(role)

        model = ExpertModel(
            before,
            goal=message(goal(before)),
            comfort=lambda: output("comfort"),
            energy=lambda: output("energy"),
        )
        client.app.state.agent_model = model
        request = SimpleNamespace(app=client.app, state=SimpleNamespace(home_id=before["home_id"]))
        task = asyncio.create_task(
            create_agent(
                request,
                AgentRequest(
                    text="60分钟客厅26度，能耗优先",
                    expected_world_id=before["world_id"],
                    strategy="expert_forecast",
                ),
                "d3-cancel-123",
            )
        )
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in entered.values())), 3)
        if completed_peer:
            await asyncio.wait_for(peer_settled.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert sorted(finished) == (["comfort"] if completed_peer else ["comfort", "energy"])
        assert not client.app.state.database.busy
        async with client.app.state.database.sessions() as session:
            saved = await session.scalar(
                select(Task).where(Task.idempotency_key == "d3-cancel-123")
            )
            run = saved.agent_run
            assert saved.status == "failed" and run["failure_code"] == "request_cancelled"
            assert run["model_calls"] == 3 and run["usage"] is None
            assert run["role_runs"][1]["status"] == "cancelled"
            assert run["role_runs"][2]["status"] == ("succeeded" if completed_peer else "cancelled")
            assert sum(r["model_calls"] for r in run["role_runs"]) == 3
            assert run["role_runs"][3]["status"] == "skipped"

    asyncio.run(exercise())
    assert home(client) == before


def test_round_six_and_task_twelve_request_limits_and_reply_clears_current_roles(client):
    before = home(client)
    count = 0

    async def coordinator():
        nonlocal count
        count += 1
        return (
            dict(kind="clarify", question="请补充偏好", options=[])
            if count % 3 == 0
            else read_message()
        )

    model = ExpertModel(before, coordinator=coordinator)
    task = expert(client, model).json()
    assert task["status"] == "waiting_input" and task["agent_run"]["model_calls"] == 6
    task = client.post(
        f"/tasks/{task['id']}/reply",
        json={"text": "能耗优先", "expected_turn": 0},
        headers={"Idempotency-Key": "d3-budget-reply-1"},
    ).json()
    assert task["status"] == "waiting_input" and task["agent_run"]["model_calls"] == 12
    task = client.post(
        f"/tasks/{task['id']}/reply",
        json={"text": "能耗优先", "expected_turn": 1},
        headers={"Idempotency-Key": "d3-budget-reply-2"},
    ).json()
    run = task["agent_run"]
    assert task["status"] == "failed" and run["failure_code"] == "task_model_budget"
    assert len(model.calls) == 12 and run["model_calls"] == 12
    assert run["goal"] is None and run["forecast"] is None
    assert [r["model_calls"] for r in run["rounds"]] == [6, 6, 0]
    assert all(r["status"] == "skipped" and r["advice"] is None for r in run["role_runs"])
    assert task["actions"] == [] and home(client) == before


@pytest.mark.parametrize("used,expected", [(9, 3), (10, 2), (11, 1), (12, 0)])
def test_atomic_budget_insufficiency_never_counts_unissued_phantom_call(used, expected):
    from homemind.agent.pipeline import run_pipeline
    from homemind.simulation.service import SimulationService

    async def exercise():
        engine = SimulationService()
        before = engine.snapshot()
        model = ExpertModel(
            before,
            goal=message(goal(before)),
            comfort=message(advice("comfort")),
            energy=message(advice("energy")),
        )
        result = await run_pipeline(
            model,
            before,
            {},
            [{"role": "user", "text": "60分钟能耗优先"}],
            engine,
            dict(
                text="60分钟能耗优先",
                strategy="expert_forecast",
                keep_entity_ids=[],
                protected_room_ids=[],
            ),
            used,
        )
        assert result["model_calls"] == expected == len(model.calls)
        assert sum(r["model_calls"] for r in result["role_runs"]) == expected
        assert result["usage"] == (
            dict(input_tokens=expected * 10, output_tokens=expected * 2) if expected else None
        )
        for role in result["role_runs"]:
            if not role["model_calls"]:
                assert (
                    role["usage"] is None
                    and role["actual_model"] is None
                    and role["advice"] is None
                )
        assert engine.snapshot() == before

    asyncio.run(exercise())


def test_zero_call_round_preserves_known_task_usage(client):
    before = home(client)
    count = 0

    async def coordinator():
        nonlocal count
        count += 1
        return (
            message(dict(kind="clarify", question="请补充", options=[]))
            if count % 3 == 0
            else read_message()
        )

    model = ExpertModel(
        before,
        goal=message(goal(before)),
        comfort=message(advice("comfort")),
        energy=message(advice("energy")),
        coordinator=coordinator,
    )
    task = expert(client, model).json()
    for turn in range(2):
        task = client.post(
            f"/tasks/{task['id']}/reply",
            json={"text": "能耗优先", "expected_turn": turn},
            headers={"Idempotency-Key": f"known-budget-reply-{turn}"},
        ).json()
    assert task["agent_run"]["model_calls"] == 12
    assert task["agent_run"]["usage"] == dict(input_tokens=92, output_tokens=20)


@pytest.mark.parametrize("drift", ["revision", "model_version"])
def test_multi_confirm_rejects_version_drift_with_zero_actions(client, drift):
    from sqlalchemy import select

    from homemind.persistence.models import Task

    before = home(client)
    task = expert(client, ExpertModel(before)).json()
    if drift == "revision":
        client.post("/simulation/advance", json={"minutes": 1})
    else:

        async def corrupt():
            async with client.app.state.database.sessions.begin() as session:
                saved = await session.scalar(select(Task).where(Task.id == task["id"]))
                run = deepcopy(saved.agent_run)
                run["forecast"]["model_version"] = "obsolete-physics"
                saved.agent_run = run

        asyncio.run(corrupt())
    baseline = home(client)
    response = client.post(
        f"/tasks/{task['id']}/confirm",
        json={"expected_turn": 0},
        headers={"Idempotency-Key": "multi-stale-confirm-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed" and response.json()["actions"] == []
    assert home(client) == baseline


def test_failed_experimental_confirmation_does_not_save_physical_records(client, monkeypatch):
    from homemind.agent import service
    from homemind.persistence import database

    before = home(client)
    task = expert(client, ExpertModel(before)).json()
    client.post("/simulation/advance", json={"minutes": 1})

    async def forbidden(*args, **kwargs):
        raise AssertionError("Failed confirmation must not save physical records")

    monkeypatch.setattr(database, "save_engine", forbidden)
    monkeypatch.setattr(service, "save_engine", forbidden)
    response = client.post(
        f"/tasks/{task['id']}/confirm",
        json={"expected_turn": 0},
        headers={"Idempotency-Key": "no-write-failed-confirm-123"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "failed" and not response.json()["actions"]


def test_multi_same_name_goal_cannot_guess_and_keeps_unrun_roles_skipped(client):
    before = home(client)
    client.patch("/simulation/rooms/" + before["rooms"][1]["id"], json={"name": "客厅"})
    before = home(client)
    task = expert(client, ExpertModel(before)).json()
    assert task["status"] == "waiting_input" and task["agent_run"]["goal"] is None
    assert len(task["agent_run"]["options"]) == 2 and task["agent_run"]["model_calls"] == 1
    assert [r["status"] for r in task["agent_run"]["role_runs"]] == [
        "succeeded",
        "skipped",
        "skipped",
        "skipped",
    ]
    assert task["actions"] == [] and home(client) == before


def test_multi_structured_response_success_is_distinct_from_plan_validation(client):
    before = home(client)
    output = selected(before, goal(before))
    output["candidate_id"] = "PRIVATE-INVALID-ID"
    task = expert(client, ExpertModel(before, coordinator=output)).json()
    assert task["status"] == "failed" and task["actions"] == [] and home(client) == before
    assert all(r["status"] == "succeeded" for r in task["agent_run"]["role_runs"])
    assert task["agent_run"]["selected_candidate_id"] is None
    assert task["agent_run"]["proposed_plan"] is None and "PRIVATE-INVALID-ID" not in str(task)


def test_mixed_rule_standard_s1_and_multi_history_remains_recoverable(client):
    before = home(client)
    ids = []
    for strategy in ("standard", "single_forecast", "expert_forecast"):
        model = (
            ExpertModel(before)
            if strategy == "expert_forecast"
            else ScriptedModel(dict(kind="refuse", reason="此需求不支持"))
        )
        response = submit(
            client,
            model,
            dict(
                text="60分钟客厅26度，能耗优先",
                expected_world_id=before["world_id"],
                strategy=strategy,
            ),
            key="mixed-" + strategy,
        )
        assert response.status_code == 200
        ids.append(response.json()["id"])
    rule = client.post(
        "/tasks",
        json=dict(scenario="away", room_ids=[before["rooms"][0]["id"]]),
        headers={"Idempotency-Key": "mixed-rule-123"},
    ).json()
    ids.append(rule["id"])
    tasks = client.get("/tasks").json()
    assert {t["mode"] for t in tasks} == {"rule", "single_agent", "multi_agent"}
    assert {t["id"] for t in tasks} == set(ids)
    assert all(client.get("/tasks/" + task_id).status_code == 200 for task_id in ids)
