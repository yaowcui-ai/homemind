"""D6 verifies prompt data contracts and actual graph boundaries, never language accuracy."""

from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage
from test_m4_agent import ScriptedModel, home
from test_product_d2 import experimental, goal, selected
from test_product_d3 import ExpertModel, expert


def test_compaction_preserves_current_facts_and_exposes_unknown_auxiliary():
    from homemind.agent.prompts import prepare_context
    from homemind.simulation.service import SimulationService

    snapshot = SimulationService().snapshot()
    room = snapshot["rooms"][0]
    auxiliary = deepcopy(next(e for e in snapshot["entities"] if e["type"] == "occupancy"))
    auxiliary.update(id="auxiliary-occupancy", name="角落辅助存在", known=False)
    snapshot["entities"].append(auxiliary)
    snapshot["recent_events"] = [{"message": "EVENT-HISTORY-NOT-CURRENT-STATE"}]
    original = deepcopy(snapshot)
    context = prepare_context({"home": snapshot, "preferences": {"fan_mode": "low"}})
    assert context["home"] == {k: v for k, v in snapshot.items() if k != "recent_events"}
    assert context["missing_observations"] == [
        dict(
            entity_id=auxiliary["id"],
            room_id=room["id"],
            name=auxiliary["name"],
            type="occupancy",
            reasons=["unknown"],
        )
    ]
    assert context["preferences"] == {"fan_mode": "low"}
    assert snapshot == original


@pytest.mark.parametrize("target,minutes", [(25, 90), (26, 60), (27, 30)])
def test_supplied_plan_contract_passes_real_goal_and_candidate_validation(target, minutes):
    from homemind.agent.forecast import forecast_plan, validate_selection
    from homemind.agent.prompts import prepare_context
    from homemind.agent.schemas import Plan
    from homemind.simulation.service import SimulationService

    engine = SimulationService()
    snapshot = engine.snapshot()
    contract = goal(snapshot, target_temperature_c=target, ready_in_minutes=minutes)
    forecast = forecast_plan(engine, contract)
    candidate = next(c for c in forecast["candidates"] if c["deadline_met"])
    facts = prepare_context({"home": snapshot, "goal": contract, "forecast": forecast})
    plan = Plan.model_validate(
        facts["required_plan_fields"]
        | dict(
            actions=candidate["actions"],
            rationale="受控模型复制实际固定字段",
        )
    ).model_dump()
    validate_selection(
        engine, dict(candidate_id=candidate["id"], plan=plan), contract, forecast, {}
    )
    assert plan["temperatures"] == [{"room_id": contract["room_id"], "target": target}]
    assert engine.snapshot() == snapshot


@pytest.mark.parametrize("strategy", ["single_forecast", "expert_forecast"])
def test_forecast_stages_use_supplied_facts_without_redundant_tools(client, strategy):
    before = home(client)
    if strategy == "single_forecast":
        model = ScriptedModel(goal(before), selected(before, goal(before)))
        task = experimental(client, model).json()
        tools = [call[1] for call in model.calls]
        expected = 2
    else:
        model = ExpertModel(before)
        task = expert(client, model).json()
        tools = [call[2] for call in model.calls]
        expected = 4
    assert task["status"] == "waiting_confirmation"
    assert len(model.calls) == expected
    assert all(definitions == [] for definitions in tools)
    assert task["actions"] == [] and home(client) == before


def test_forecast_selection_rejects_unsolicited_tool_without_followup_or_actions(client):
    before = home(client)
    read = AIMessage(
        content="",
        tool_calls=[
            dict(id="redundant", name="read_home", args={}, type="tool_call"),
        ],
    )
    model = ScriptedModel(goal(before), read, selected(before, goal(before)))
    task = experimental(client, model).json()
    assert task["status"] == "failed"
    assert task["agent_run"]["failure_code"] == "invalid_tool"
    assert len(model.calls) == 2
    assert task["actions"] == [] and home(client) == before
