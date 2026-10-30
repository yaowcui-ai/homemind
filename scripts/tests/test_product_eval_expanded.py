"""Protocol guarantees, not claims about language-model accuracy."""

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts/product_eval_expanded.py"


def module():
    assert SCRIPT.is_file(), "Expanded evaluator must exist"
    spec = importlib.util.spec_from_file_location("expanded_eval", SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_default_is_offline_and_schedule_has_120_distinct_runs():
    m = module()
    response = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert response.returncode == 0, response.stderr
    assert json.loads(response.stdout) == {
        "status": "not_run",
        "development_cases": 24,
        "holdout_cases": 12,
        "planned_runs": 120,
        "limit": 360,
        "real_requests": 0,
    }
    runs = m.schedule()
    assert len(runs) == len(set(runs)) == 120
    assert sum(r[0] == "baseline" for r in runs) == 48
    assert sum(r[0] == "candidate" for r in runs) == 48
    assert sum(r[0] == "holdout" for r in runs) == 24


def test_six_families_and_multiple_targets_are_declared_before_calls():
    cases = module().load_cases()
    assert len(cases) == len({c["id"] for c in cases}) == len({c["text"] for c in cases}) == 36
    families = {c["family"] for c in cases}
    assert len(families) == 6
    for family in families:
        assert sum(c["family"] == family and c["split"] == "development" for c in cases) == 4
        assert sum(c["family"] == family and c["split"] == "holdout" for c in cases) == 2
    assert len({c["target_temperature_c"] for c in cases}) >= 3
    assert sum(bool(c.get("reply")) for c in cases) == 6


def test_budget_is_new_shared_360_with_journey_headroom(tmp_path):
    m = module()
    ledger = m.open_budget(tmp_path / "budget.json", "frozen", resume=False)
    for _ in range(350):
        ledger.reserve("counted")
    assert m.can_start(ledger, {"reply": "补答"}) is False
    assert m.can_start(ledger, {}) is True
    for _ in range(10):
        ledger.reserve("counted")
    with pytest.raises(m.d5.d4.base.BudgetExceeded):
        ledger.reserve("blocked")
    with pytest.raises(ValueError):
        m.open_budget(ledger.path, "changed", resume=True)


def test_model_contract_target_is_not_hardcoded_to_26():
    import product_eval_d5 as d5

    snapshot = {
        "rooms": [{"name": "测试房", "id": "r1"}, {"name": "其他", "id": "r2"}],
        "entities": [{"id": t, "type": t, "room_id": "r1"} for t in ("climate", "cover", "light")],
    }
    case = dict(
        room="测试房",
        target_temperature_c=27,
        minutes=60,
        priority="energy_first",
        fans=["low"],
        cover="keep",
    )
    gold = d5.gold_from_snapshot(case, snapshot)
    assert gold["target_temperature_c"] == 27
    plan = dict(
        actions=[{"entity_id": "climate"}],
        ready_in_minutes=60,
        temperatures=[{"room_id": "r1", "target": 27}],
        keep_entity_ids=["light"],
        protected_room_ids=["r2"],
    )
    task = {"agent_run": {"goal": gold, "selected_candidate_id": "c1", "proposed_plan": plan}}
    forecast = {"candidates": [{"id": "c1", "deadline_met": True, "actions": plan["actions"]}]}
    assert d5.d4.hard_plan_matches(task, gold, forecast)
    plan["temperatures"][0]["target"] = 26
    assert not d5.d4.hard_plan_matches(task, gold, forecast)


def test_real_mode_cannot_start_without_bound_authorization(tmp_path):
    m = module()
    with pytest.raises(ValueError, match="authorization"):
        m.require_authorization(tmp_path)


def test_baseline_prompt_is_bound_to_frozen_git_version(monkeypatch, tmp_path):
    m = module()
    monkeypatch.setattr(m, "BATCH", tmp_path)
    pipeline = m.load_baseline_pipeline()
    assert (
        pipeline.__globals__["run_planner"].__globals__["forecast_prompt"].__module__
        == "expanded_baseline_prompts"
    )
    assert pipeline.__globals__["planner_graph"].run_planner is pipeline.__globals__["run_planner"]


@pytest.mark.parametrize("strategy", ["single_forecast", "expert_forecast"])
def test_scripted_clarification_resumes_same_task_and_binds_review(strategy, monkeypatch, tmp_path):
    from langchain_core.messages import AIMessage
    from test_product_eval_d5 import ControlledModel

    m = module()
    monkeypatch.setattr(m, "BATCH", tmp_path)
    case = next(c for c in m.load_cases() if c["id"] == "X21")

    class JourneyModel(ControlledModel):
        first = True

        async def ainvoke(self, messages, tools):
            if self.first:
                self.first = False
                return AIMessage(
                    content=json.dumps(
                        dict(kind="clarify", question="舒适和节能哪个优先？", options=[])
                    )
                )
            return await super().ainvoke(messages, tools)

    with m.d5.d4.base.official_http_only():
        record = m.run_trial(case, "controlled", strategy, JourneyModel(case))
    assert record["source"] == "controlled_test"
    assert record["first_task"]["status"] == "waiting_input"
    assert record["journey"]["replied"]
    assert record["first_task"]["id"] == record["final_task"]["id"]
    assert record["final_task"]["status"] == "succeeded"
    assert not record["score"]["case_pass"]  # Needs a separate bound semantic review.
    review = dict(
        **record["review_binding"],
        correct=True,
        reviewer="controlled-test-only",
        reason="Known fixture question asks priority",
    )
    assert m.score_record(record, case, review)["journey_completed"]
    tampered = deepcopy(record)
    tampered["first_task"]["agent_run"]["question"] = "放宽温度吗？"
    assert not m.score_record(tampered, case, review)["case_pass"]
