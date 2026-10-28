"""Second-round budget, frozen samples and continuation checks; no real HTTP."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "product_eval_c2.py"


def module():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("product_eval_c2", SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_default_does_not_load_config_or_call_model():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data == {"status": "not_run", "cases": 12, "new_cases": 8, "real_requests": 0}


def test_original_four_cases_and_expected_answers_are_unchanged():
    m = module()
    originals = {c["id"]: c for c in m.base.load_cases()}
    cases = m.load_cases()
    assert len(cases) == len({c["id"] for c in cases}) == 12
    for case in cases[:4]:
        assert case == originals[case["id"]]
    assert {c["id"] for c in cases[4:]} == {f"C{i}" for i in range(37, 45)}


def test_shared_32_budget_survives_new_phase_and_never_resets(tmp_path):
    m = module()
    path = tmp_path / "budget.json"
    first = m.open_budget(path, "frozen", resume=False)
    for _ in range(30):
        first.reserve("phase1/C14")
    with pytest.raises(FileExistsError):
        m.open_budget(path, "frozen", resume=False)
    second = m.open_budget(path, "frozen", resume=True)
    assert second.used == 30 and second.data["limit"] == 32
    second.reserve("phase2/C14")
    second.reserve("phase2/C14")
    with pytest.raises(m.base.BudgetExceeded):
        second.reserve("phase2/C14")
    assert json.loads(path.read_text())["used"] == 32
    with pytest.raises(ValueError):
        m.open_budget(path, "changed_expected", resume=True)


def test_retest_only_selects_recorded_failures_not_successes_or_unrun_cases():
    m = module()
    cases = m.load_cases()
    records = [
        {"case_id": "C14", "score": {"case_pass": False}},
        {"case_id": "C06", "score": {"case_pass": True}},
    ]
    assert [c["id"] for c in m.select_retests(cases, records, ["C14"])] == ["C14"]
    for requested in (["C06"], ["C44"], ["C14", "C14"], ["fiction"]):
        with pytest.raises(ValueError):
            m.select_retests(cases, records, requested)


@pytest.mark.parametrize("foreign_reply", [False, True])
def test_free_answer_continues_same_task_and_keeps_predeclared_metrics(
    tmp_path, monkeypatch, foreign_reply
):
    m = module()
    sys.path.insert(0, str(SCRIPT.parents[1] / "backend/src"))
    from langchain_core.messages import AIMessage, ToolMessage

    class Controlled:
        rounds = 0

        async def ainvoke(self, messages, _tools):
            reads = [item for item in messages if isinstance(item, ToolMessage)]
            if not reads:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "read_home", "id": "read", "args": {}, "type": "tool_call"}
                    ],
                )
            self.rounds += 1
            if self.rounds == 1:
                return AIMessage(
                    content=json.dumps(
                        {"kind": "clarify", "question": "选择开灯还是关灯？", "options": []}
                    )
                )
            home = json.loads(reads[-1].content)
            lamp = next(e for e in home["entities"] if e["name"] == "客厅主灯")
            return AIMessage(
                content=json.dumps(
                    {
                        "kind": "plan",
                        "scenario": "local",
                        "room_ids": [lamp["room_id"]],
                        "keep_entity_ids": [],
                        "protected_room_ids": [],
                        "actions": [
                            {
                                "entity_id": lamp["id"],
                                "room_id": lamp["room_id"],
                                "action": "set_light",
                                "parameters": {"power": False},
                            }
                        ],
                        "temperatures": [],
                        "ready_in_minutes": None,
                        "rationale": "按回答关灯",
                    }
                )
            )

    case = next(c for c in m.load_cases() if c["id"] == "C40")
    if foreign_reply:
        original = m.base.checked

        def changed_id(response):
            data = original(response)
            if isinstance(data, dict) and (data.get("agent_run") or {}).get("turn", 0) > 0:
                data["id"] = "unexpected-other-task"
            return data

        monkeypatch.setattr(m.base, "checked", changed_id)
    with m.base.official_http_only():
        result = m.base.run_case(case, Controlled(), tmp_path / "free-answer.db")
    assert result["score"]["case_pass"] is (not foreign_reply)
    assert result["score"]["same_task_after_reply"] is (not foreign_reply)
    assert result["score"]["goal_completed"] and result["score"]["exception_correct"]
    assert result["final_task"]["agent_run"]["model_calls"] == 4


def test_authorized_batch_directory_is_fixed(tmp_path):
    m = module()
    with pytest.raises(ValueError):
        m.validate_batch(tmp_path)
    assert m.validate_batch(m.BATCH) == m.BATCH.resolve()


def test_choice_clarification_cannot_substitute_a_room_option_for_on_off_answer():
    m = module()
    case = {"expected": {"kind": "clarify", "require_empty_options": True}}
    task = {
        "status": "waiting_input",
        "actions": [],
        "agent_run": {"question": "开灯还是关灯？", "options": [{"id": "room-1", "kind": "room"}]},
    }
    assert not m.base.score_case(case, task, {})["case_pass"]


def test_retest_excludes_script_errors_and_requires_a_recorded_source_change():
    m = module()
    cases = m.load_cases()
    with pytest.raises(ValueError):
        m.select_retests(
            cases,
            [{"case_id": "C14", "error": "evaluation_case_error", "score": {"case_pass": False}}],
            ["C14"],
        )
    first = {"hashes": {"cases": "frozen", "graph": "before"}, "model": "same"}
    with pytest.raises(ValueError):
        m.validate_retest_version(first, first["hashes"], "same")
    with pytest.raises(ValueError):
        m.validate_retest_version(first, {"cases": "frozen", "graph": "after"}, "other")
    m.validate_retest_version(first, {"cases": "frozen", "graph": "after"}, "same")
