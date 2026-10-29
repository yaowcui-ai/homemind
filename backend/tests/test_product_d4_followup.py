"""Finite failure diagnostics; injected model tests are not old failure evidence."""

import asyncio
import json

import pytest
from test_m4_agent import ScriptedModel, home, submit
from test_product_d2 import goal, selected
from test_product_d3 import ExpertModel, advice, expert

from homemind.agent.graph import run_planner
from homemind.agent.schemas import GOAL_OUTPUT


@pytest.mark.parametrize(
    "output,path,category",
    [
        (dict(kind="clarify", question="PRIVATE-REJECTED-QUESTION"), "$.options", "missing"),
        (
            dict(
                kind="clarify",
                question="PRIVATE-REJECTED-QUESTION",
                options=[],
                **{"PRIVATE-KEY": "PRIVATE-VALUE"},
            ),
            "$.<field>",
            "extra_forbidden",
        ),
        ("PRIVATE-NOT-JSON", "$", "json_invalid"),
    ],
)
def test_schema_records_are_bounded_and_do_not_echo_rejected_values(output, path, category):
    model = ScriptedModel(output) if isinstance(output, dict) else ScriptedModelRaw(output)
    result = asyncio.run(
        run_planner(model, {}, {}, [], output_adapter=GOAL_OUTPUT, goal_stage=True)
    )
    assert result["failure_code"] == "invalid_output" and result["output"] is None
    records = json.dumps(result["records"], ensure_ascii=False)
    assert path in records and category in records and "coordinator_goal" in records
    assert "PRIVATE" not in json.dumps(result)


class ScriptedModelRaw:
    def __init__(self, text):
        self.text = text

    async def ainvoke(self, *_args):
        from langchain_core.messages import AIMessage

        return AIMessage(content=self.text)


@pytest.mark.parametrize(
    "changes,path,category",
    [
        ({"role": "energy"}, "$.role", "role_mismatch"),
        ({"evidence_refs": ["candidate:PRIVATE-ID"]}, "$.evidence_refs", "unknown_evidence"),
        ({"preferred_candidate_id": "PRIVATE-ID"}, "$.preferred_candidate_id", "unknown_candidate"),
        ({"evidence_refs": ["goal"]}, "$.evidence_refs", "missing_candidate_evidence"),
    ],
)
def test_advice_diagnostic_survives_task_persistence_without_bad_values(
    client, changes, path, category
):
    before = home(client)
    rejected = advice("comfort")
    rejected.update(changes)
    task = expert(client, ExpertModel(before, comfort=rejected)).json()
    assert task["status"] == "failed" and task["agent_run"]["failure_code"] == "analysis_incomplete"
    assert not task["actions"] and home(client) == before
    records = json.dumps(task["agent_run"]["records"])
    assert path in records and category in records and "comfort" in records
    assert "PRIVATE" not in json.dumps(task)
    assert (
        client.get("/tasks/" + task["id"]).json()["agent_run"]["records"]
        == task["agent_run"]["records"]
    )


def test_selection_drift_names_only_static_field_and_keeps_failure_zero_write(client):
    before = home(client)
    extracted = goal(before)
    output = selected(before, extracted)
    output["plan"]["keep_entity_ids"] = ["PRIVATE-BAD-KEEP"]
    task = submit(
        client,
        ScriptedModel(extracted, output),
        dict(
            text="60分钟客厅26度，能耗优先",
            expected_world_id=before["world_id"],
            strategy="single_forecast",
        ),
    ).json()
    assert task["status"] == "failed" and task["agent_run"]["failure_code"] == "goal_drift"
    assert not task["actions"] and home(client) == before
    assert "$.plan.keep_entity_ids" in json.dumps(task["agent_run"]["records"])
    assert "PRIVATE" not in json.dumps(task)


def test_clarification_shape_is_explicit_in_goal_stage():
    model = ScriptedModel(dict(kind="clarify", question="请先恢复缺失读数", options=[]))
    result = asyncio.run(
        run_planner(
            model,
            {},
            {},
            [],
            output_adapter=GOAL_OUTPUT,
            public_context={"home": {}},
            goal_stage=True,
        )
    )
    assert result["output"]["kind"] == "clarify"
    prompt = model.calls[0][0][0].content
    assert "Never omit options" in prompt
    assert "For missing readings" in prompt


def test_selection_stage_demands_exact_goal_keep_lists():
    from homemind.agent.schemas import SELECTION_OUTPUT

    model = ScriptedModel(dict(kind="refuse", reason="受控提示测试"))
    asyncio.run(
        run_planner(
            model,
            {},
            {},
            [],
            output_adapter=SELECTION_OUTPUT,
            public_context={"goal": {}, "forecast": {}},
        )
    )
    prompt = model.calls[0][0][0].content
    assert "Copy keep_entity_ids and protected_room_ids exactly from GoalContract" in prompt
    assert "do not add or remove IDs" in prompt
