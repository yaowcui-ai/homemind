"""Controlled regressions for the real C12/C40 clarification failures, no model HTTP."""

import json

import pytest
from test_m4_agent import ScriptedModel, home, plan, submit


@pytest.mark.parametrize("kind", ["entity", "room"])
def test_duplicate_option_rejected_without_saving_unvalidated_question(client, kind):
    before = home(client)
    item = before["rooms"][0] if kind == "room" else before["entities"][0]
    output = {
        "kind": "clarify",
        "question": "private rejected duplicate question",
        "options": [
            {"kind": kind, "id": item["id"], "label": "private first choice"},
            {"kind": kind, "id": item["id"], "label": "private second choice"},
        ],
    }
    task = submit(client, ScriptedModel(output)).json()
    assert task["status"] == "failed" and task["actions"] == []
    assert task["agent_run"]["failure_code"] == "duplicate_option"
    assert task["agent_run"]["diagnostic"] == {
        "phase": "validation",
        "output_kind": "clarify",
        "code": "duplicate_option",
        "field_path": "$.options[1].id",
        "reference_kind": kind,
        "reference_in_current_home": True,
    }
    assert task["agent_run"]["question"] is None and task["agent_run"]["options"] == []
    assert "private" not in json.dumps(task)
    assert client.get(f"/tasks/{task['id']}").json() == task
    assert home(client) == before


@pytest.mark.parametrize("mixed", [False, True])
def test_distinct_real_object_options_remain_usable(client, mixed):
    before = home(client)
    options = [
        {"kind": "room", "id": room["id"], "label": "model label"} for room in before["rooms"]
    ]
    if mixed:
        options[1] = {"kind": "entity", "id": before["entities"][0]["id"], "label": "model label"}
    task = submit(
        client, ScriptedModel({"kind": "clarify", "question": "请选择对象", "options": options})
    ).json()
    assert task["status"] == "waiting_input" and task["actions"] == []
    assert [(o["kind"], o["id"]) for o in task["agent_run"]["options"]] == [
        (o["kind"], o["id"]) for o in options
    ]
    assert all(o["label"] != "model label" for o in task["agent_run"]["options"])
    assert home(client) == before


def test_prompt_asks_to_relax_hard_conflict_with_free_text_choice_in_same_task(client):
    before = home(client)
    question = {
        "kind": "clarify",
        "question": "主灯亮度80%与保持所有灯不变互斥，请选择放宽哪一条要求？",
        "options": [],
    }
    chosen = plan(before)
    chosen["actions"][0]["parameters"] = {"brightness_pct": 80}
    model = ScriptedModel(question, chosen)
    task = submit(
        client,
        model,
        body={
            "text": "主灯亮度80%，同时保持所有灯不变，两条都是硬要求",
            "expected_world_id": before["world_id"],
        },
    ).json()
    prompt = model.calls[0][0][0].content
    assert "even if the user calls both requirements mandatory" in prompt
    assert "options=[]" in prompt
    assert "same entity ID" in prompt
    assert '"question":"主灯开启与保持关闭互斥，请选择放宽哪一条要求？","options":[]' in prompt
    assert task["status"] == "waiting_input" and task["actions"] == []
    assert home(client) == before
    replied = client.post(
        f"/tasks/{task['id']}/reply",
        json={"text": "放宽保持所有灯不变，只调主灯亮度80%", "expected_turn": 0},
        headers={"Idempotency-Key": "phase2-conflict-reply"},
    ).json()
    assert replied["id"] == task["id"] and replied["status"] == "succeeded"
    assert len(replied["actions"]) == 1 and replied["actions"][0]["parameters"] == {
        "brightness_pct": 80
    }
