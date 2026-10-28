"""Product-evaluation safeguards and independent oracles; no real provider calls."""

import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "product_eval.py"


def module():
    spec = importlib.util.spec_from_file_location("product_eval", SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_default_only_lists_cases_without_importing_backend_or_reading_settings():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["real_requests"] == 0 and body["cases"] >= 36
    assert body["status"] == "not_run"


def test_budget_is_persistent_and_cannot_be_overwritten(tmp_path):
    m = module()
    path = tmp_path / "ledger.json"
    ledger = m.BudgetLedger(path, limit=2, fingerprint="fixed")
    assert ledger.reserve("C01") == 1
    with pytest.raises(FileExistsError):
        m.BudgetLedger(path, limit=2, fingerprint="fixed")
    resumed = m.BudgetLedger(path, limit=2, fingerprint="fixed", resume=True)
    assert resumed.reserve("C02") == 2
    with pytest.raises(m.BudgetExceeded):
        resumed.reserve("C03")
    assert json.loads(path.read_text())["used"] == 2
    with pytest.raises(ValueError):
        m.BudgetLedger(path, limit=40, fingerprint="fixed", resume=True)
    with pytest.raises(ValueError):
        m.BudgetLedger(path, limit=2, fingerprint="changed", resume=True)


def test_failed_requests_consume_budget_without_recording_private_response(tmp_path):
    m = module()
    ledger = m.BudgetLedger(tmp_path / "budget.json", limit=1, fingerprint="x")

    class FailingModel:
        async def ainvoke(self, _messages, _tools):
            raise RuntimeError("synthetic provider exception with private body")

    bounded = m.BudgetedModel(FailingModel(), ledger)
    bounded.case_id = "C01"
    with pytest.raises(RuntimeError):
        asyncio.run(bounded.ainvoke([], []))
    with pytest.raises(m.BudgetExceeded):
        asyncio.run(bounded.ainvoke([], []))
    saved = ledger.path.read_text()
    assert ledger.used == 1 and "private" not in saved


def test_oracle_does_not_accept_successful_wrong_device_or_extra_writes():
    m = module()
    bindings = {"living_light": "l1", "bedroom_light": "l2"}
    case = {
        "expected": {
            "kind": "execute",
            "actions": [{"selector": "living_light", "parameters": {"power": False}}],
        }
    }
    task = {
        "status": "succeeded",
        "plan": {"actions": [{"entity_id": "l2", "parameters": {"power": False}}]},
        "actions": [],
        "verification": {"conditions": []},
    }
    assert not m.score_case(case, task, bindings)["understanding_correct"]
    task["plan"]["actions"].append({"entity_id": "l1", "parameters": {"power": False}})
    assert not m.score_case(case, task, bindings)["understanding_correct"]


def test_correct_clarification_is_not_counted_as_goal_completion():
    m = module()
    score = m.score_case(
        {"expected": {"kind": "clarify"}},
        {
            "status": "waiting_input",
            "actions": [],
            "agent_run": {
                "question": "选哪间？",
                "options": [{"id": "r1"}, {"id": "r2"}],
            },
        },
        {},
    )
    assert score["case_pass"] and score["exception_correct"]
    assert score["goal_completed"] is None


def test_normal_task_rejection_is_not_a_successful_exception():
    m = module()
    score = m.score_case(
        {"expected": {"kind": "execute", "actions": []}},
        {"status": "failed", "plan": {"actions": []}, "actions": []},
        {},
    )
    assert not score["case_pass"] and score["exception_correct"] is None


def test_unknown_readback_is_not_goal_or_joint_action_success():
    m = module()
    case = {
        "expected": {
            "kind": "execute",
            "actions": [{"selector": "lamp", "parameters": {"power": False}}],
        }
    }
    task = {
        "status": "partial",
        "plan": {"actions": [{"entity_id": "l1", "parameters": {"power": False}}]},
        "actions": [{"entity_id": "l1", "status": "unknown"}],
        "verification": {"conditions": []},
    }
    result = m.score_case(case, task, {"lamp": "l1"})
    assert result["understanding_correct"] and not result["goal_completed"]
    assert not result["all_actions_verified"] and not result["case_pass"]


def test_all_product_cases_have_traceable_requirements_and_expected_behavior():
    cases = module().load_cases()
    assert len(cases) >= 36 and len({case["id"] for case in cases}) == len(cases)
    assert all(case["goal"] and case["requirements"] and case["expected"] for case in cases)
    assert sum(case["source"] == "real_candidate" for case in cases) >= 16
    assert all(case.get("evidence_test") for case in cases if case["source"] == "regression")


def test_official_network_guard_rejects_trace_and_other_domains():
    import httpx

    async def attempt():
        async with httpx.AsyncClient() as client:
            await client.post("https://api.smith.langchain.com/runs", json={})

    with (
        module().official_http_only(),
        pytest.raises(RuntimeError, match="endpoint_blocked"),
    ):
        asyncio.run(attempt())


def test_controlled_model_exercises_real_api_graph_and_independent_readback(tmp_path):
    sys.path.insert(0, str(SCRIPT.parents[1] / "backend" / "src"))
    from langchain_core.messages import AIMessage, ToolMessage

    class Controlled:
        async def ainvoke(self, messages, _tools):
            reads = [m for m in messages if isinstance(m, ToolMessage)]
            if not reads:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "test-read",
                            "name": "read_home",
                            "args": {},
                            "type": "tool_call",
                        }
                    ],
                )
            snapshot = json.loads(reads[-1].content)
            lamp = next(e for e in snapshot["entities"] if e["name"] == "客厅主灯")
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
                        "rationale": "只关指定灯",
                    }
                )
            )

    m = module()
    with m.official_http_only():
        result = m.run_case(m.load_cases()[0], Controlled(), tmp_path / "synthetic.db")
    assert result["score"]["case_pass"]
    assert result["final_task"]["agent_run"]["model_calls"] == 2
    assert result["final_task"]["actions"][0]["status"] == "verified"


def test_sparse_fan_cannot_change_temperature_even_when_task_reports_success():
    m = module()
    expected = {
        "kind": "execute",
        "preserve_unspecified": True,
        "actions": [{"selector": "climate", "parameters": {"fan_mode": "low"}}],
    }
    task = {
        "plan": {
            "actions": [
                {
                    "entity_id": "c1",
                    "parameters": {"fan_mode": "low", "target_temperature_c": 24},
                }
            ]
        },
        "initial_snapshot": {"entities": [{"id": "c1", "state": {"target_temperature_c": 26}}]},
    }
    assert not m.matches_plan(expected, task, {"climate": "c1"})


def test_script_error_keeps_denominators_and_is_separate_from_model_failure(tmp_path):
    m = module()
    ledger = m.BudgetLedger(tmp_path / "ledger.json", limit=40, fingerprint="x")
    execute, blocked = m.load_cases()[0], m.load_cases()[12]
    records = [
        m.failed_record(execute, "evaluation_case_error", "ValueError"),
        m.failed_record(blocked, "interrupted_no_replay"),
    ]
    summary = m.summarize(records, ledger, [execute, blocked])
    assert summary["metrics"]["understanding_correct"] == {
        "numerator": 0,
        "denominator": 1,
    }
    assert summary["metrics"]["goal_completed"] == {"numerator": 0, "denominator": 1}
    assert summary["metrics"]["exception_correct"] == {"numerator": 0, "denominator": 1}
    assert summary["script_errors"] == ["C01", "C13"]


def test_duplicate_actual_actions_cannot_hide_a_missing_device():
    m = module()
    case = {
        "expected": {
            "kind": "execute",
            "actions": [
                {"selector": "a", "parameters": {"power": False}},
                {"selector": "b", "parameters": {"power": False}},
            ],
        }
    }
    task = {
        "status": "succeeded",
        "plan": {
            "actions": [
                {"entity_id": "a1", "parameters": {"power": False}},
                {"entity_id": "b1", "parameters": {"power": False}},
            ]
        },
        "actions": [
            {"entity_id": "a1", "status": "verified"},
            {"entity_id": "a1", "status": "verified"},
        ],
    }
    score = m.score_case(case, task, {"a": "a1", "b": "b1"})
    assert not score["case_pass"] and not score["goal_completed"]
    assert not score["all_actions_verified"] and score["false_success"]


def test_failed_clarification_keeps_predeclared_followup_goal_denominators():
    m = module()
    case = next(c for c in m.load_cases() if c["id"] == "C11")
    task = {"status": "failed", "actions": [], "agent_run": {"failure_code": "refused"}}
    score = m.score_case(case, task, {})
    assert score["understanding_correct"] is False
    assert score["goal_completed"] is False and score["all_actions_verified"] is False
    assert m.failed_record(case, "script_error")["score"]["goal_completed"] is False
    assert m.failed_record(case, "script_error")["score"]["exception_correct"] is False


def test_retest_uses_remaining_original_budget_and_frozen_cases(tmp_path):
    m = module()
    m.BudgetLedger(tmp_path / "budget.json", limit=2, fingerprint="old").reserve("C01")
    manifest = {"hashes": {"evaluation/product-c-cases.json": "frozen"}}
    write = tmp_path / "manifest.json"
    write.write_text(json.dumps(manifest), encoding="utf-8")
    resumed = m.retest_ledger(tmp_path, "frozen")
    assert resumed.used == 1 and resumed.reserve("C01-r2") == 2
    with pytest.raises(m.BudgetExceeded):
        resumed.reserve("C01-r2")
    with pytest.raises(ValueError):
        m.retest_ledger(tmp_path, "changed_expected_answers")
