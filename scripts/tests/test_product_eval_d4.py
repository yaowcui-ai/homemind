"""D4 independent scoring and pair isolation; never a real provider call."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "product_eval_d4.py"


def module():
    sys.path.insert(0, str(SCRIPT.parent))
    sys.path.insert(0, str(SCRIPT.parents[1] / "backend/src"))
    spec = importlib.util.spec_from_file_location("product_eval_d4", SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_default_is_no_config_no_network():
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "status": "not_run",
        "cases": 6,
        "strategies": 2,
        "real_requests": 0,
    }


def test_budget_is_fixed_shared_40_and_cannot_reset(tmp_path):
    m = module()
    ledger = m.open_budget(tmp_path / "budget.json", "fixed", resume=False)
    for _ in range(40):
        ledger.reserve("phase1/DD01/single_forecast")
    with pytest.raises(m.base.BudgetExceeded):
        ledger.reserve("phase2/DD01/expert_forecast")
    with pytest.raises(FileExistsError):
        m.open_budget(ledger.path, "fixed", resume=False)
    assert m.open_budget(ledger.path, "fixed", resume=True).used == 40
    with pytest.raises(ValueError):
        m.validate_batch(tmp_path)


def test_no_round_starts_without_its_maximum_six_remaining_requests(tmp_path):
    m = module()
    ledger = m.open_budget(tmp_path / "budget.json", "fixed", resume=False)
    for _ in range(34):
        ledger.reserve("prior")
    assert m.can_start_trial(ledger)
    ledger.reserve("prior")
    assert not m.can_start_trial(ledger)


def test_equivalent_optima_and_missing_selection_are_scored_independently():
    m = module()
    forecast = {
        "candidates": [
            {"id": "a", "deadline_met": True, "first_observed_goal_minute": 17, "energy_wh": 10},
            {"id": "b", "deadline_met": True, "first_observed_goal_minute": 17, "energy_wh": 10},
            {"id": "c", "deadline_met": True, "first_observed_goal_minute": 20, "energy_wh": 10},
            {"id": "d", "deadline_met": False, "first_observed_goal_minute": None, "energy_wh": 0},
        ]
    }
    assert m.optimal_ids(forecast, "comfort_first") == ["a", "b"]
    assert not m.preference_correct(None, forecast, "comfort_first")
    assert not m.preference_correct("c", forecast, "comfort_first")


def test_pair_is_exact_clone_with_gold_hidden_from_models(tmp_path):
    m = module()
    from serve_agent_e2e import ControlledBrowserModel

    case = m.load_cases()[1]
    with m.base.official_http_only():
        pair = m.prepare_pair(case, tmp_path)
        results = [
            m.run_trial(case, strategy, pair, ControlledBrowserModel()) for strategy in m.STRATEGIES
        ]
    assert results[0]["initial_snapshot"] == results[1]["initial_snapshot"]
    assert all(r["score"]["case_pass"] for r in results)
    assert [r["final_task"]["agent_run"]["model_calls"] for r in results] == [2, 4]
    assert all(r["score"]["confirmation_observed"] for r in results)
    assert all(r["score"]["goal_completed"] for r in results)
    assert all(
        r["scope_energy_wh"]
        == next(
            c["energy_wh"]
            for c in pair["forecast"]["candidates"]
            if c["id"] == r["final_task"]["agent_run"]["selected_candidate_id"]
        )
        for r in results
    )


def test_scorer_catches_false_success_wrong_contract_and_foreign_writes(tmp_path):
    m = module()
    from serve_agent_e2e import ControlledBrowserModel

    case = m.load_cases()[1]
    with m.base.official_http_only():
        pair = m.prepare_pair(case, tmp_path)
        result = m.run_trial(case, m.STRATEGIES[0], pair, ControlledBrowserModel())
    task = result["final_task"]
    task["agent_run"]["goal"]["priority"] = "comfort_first"
    score = m.score(
        case,
        task,
        pair["gold"],
        pair["forecast"],
        result["initial_snapshot"],
        result["final_snapshot"],
        True,
    )
    assert not score["goal_completed"] and not score["case_pass"] and score["false_success"]
    task["agent_run"]["goal"] = pair["gold"]
    lamp = next(e for e in result["final_snapshot"]["entities"] if e["type"] == "light")
    lamp["state"]["power"] = not lamp["state"]["power"]
    assert not m.score(
        case,
        task,
        pair["gold"],
        pair["forecast"],
        result["initial_snapshot"],
        result["final_snapshot"],
        True,
    )["case_pass"]


class ControlledD4Model:
    """Exact six-case fixture; not NL capability or real model evidence."""

    calls = 0

    async def ainvoke(self, messages, tools):
        from langchain_core.messages import AIMessage, HumanMessage

        self.calls += 1
        prompt = messages[0].content
        facts, _ = json.JSONDecoder().raw_decode(prompt.split("Frozen public context: ", 1)[1])
        assert "gold" not in facts and "oracle_forecast" not in facts
        if "forecast" not in facts:
            original = next(
                json.loads(m.content)["text"] for m in messages if isinstance(m, HumanMessage)
            )
            case = next(c for c in module().load_cases() if c["text"] == original)
            rooms = {r["name"]: r["id"] for r in facts["home"]["rooms"]}
            entities = facts["home"]["entities"]
            devices = {e["type"]: e["id"] for e in entities if e["room_id"] == rooms["客厅"]}
            keeps = [e["id"] for e in entities if e["name"] == "卧室阅读灯"]
            if case["cover"] == "keep":
                keeps.append(devices["cover"])
            output = dict(
                kind="goal",
                room_id=rooms["客厅"],
                climate_entity_id=devices["climate"],
                cover_entity_id=devices["cover"],
                target_temperature_c=26,
                ready_in_minutes=case["minutes"],
                priority=case["priority"],
                allowed_fan_modes=case["fans"],
                cover_constraint=case["cover"],
                keep_entity_ids=keeps,
                protected_room_ids=[rooms["卧室"]],
            )
        else:
            role = facts.get("role")
            priority = {"comfort": "comfort_first", "energy": "energy_first"}.get(
                role, facts["goal"]["priority"]
            )
            candidate_id = module().optimal_ids(facts["forecast"], priority)[0]
            if role in {"comfort", "energy"}:
                output = dict(
                    role=role,
                    outcome="recommend",
                    preferred_candidate_id=candidate_id,
                    evidence_refs=["candidate:" + candidate_id],
                    public_summary="受控夹具，不代表真实模型",
                )
            else:
                candidate = next(
                    c for c in facts["forecast"]["candidates"] if c["id"] == candidate_id
                )
                goal = facts["goal"]
                output = dict(
                    kind="selection",
                    candidate_id=candidate_id,
                    plan=dict(
                        kind="plan",
                        scenario="homecoming",
                        room_ids=[goal["room_id"]],
                        keep_entity_ids=goal["keep_entity_ids"],
                        protected_room_ids=goal["protected_room_ids"],
                        actions=candidate["actions"],
                        temperatures=[dict(room_id=goal["room_id"], target=26)],
                        ready_in_minutes=goal["ready_in_minutes"],
                        rationale="受控测试选择",
                    ),
                )
        return AIMessage(content=json.dumps(output))


@pytest.mark.parametrize("index", range(6))
def test_all_development_pairs_and_original_choices(index, tmp_path):
    m = module()
    case = m.load_cases()[index]
    with m.base.official_http_only():
        pair = m.prepare_pair(case, tmp_path)
        results = [
            m.run_trial(case, strategy, pair, ControlledD4Model()) for strategy in m.STRATEGIES
        ]
    assert all(r["score"]["case_pass"] for r in results), results[0]["score"]
    assert results[0]["initial_snapshot"] == results[1]["initial_snapshot"]
    if case["id"] == "DD05":
        assert len(pair["gold"]["keep_entity_ids"]) == 2
        assert all(c["cover_position_pct"] == 50 for c in pair["forecast"]["candidates"])
        assert all(len(r["final_task"]["actions"]) == 1 for r in results)


def test_preference_suboptimal_original_choice_is_executed_and_remains_a_failure(tmp_path):
    m = module()

    class Suboptimal(ControlledD4Model):
        async def ainvoke(self, messages, tools):
            response = await super().ainvoke(messages, tools)
            output = json.loads(response.content)
            if output.get("kind") == "selection":
                facts, _ = json.JSONDecoder().raw_decode(
                    messages[0].content.split("Frozen public context: ", 1)[1]
                )
                candidate = facts["forecast"]["candidates"][0]
                output["candidate_id"] = candidate["id"]
                output["plan"]["actions"] = candidate["actions"]
                response.content = json.dumps(output)
            return response

    with m.base.official_http_only():
        case = m.load_cases()[1]
        pair = m.prepare_pair(case, tmp_path)
        result = m.run_trial(case, m.STRATEGIES[0], pair, Suboptimal())
    assert result["final_task"]["agent_run"]["selected_candidate_id"] == "c1"
    assert result["score"]["goal_completed"] and result["scope_energy_wh"] == 550.05
    assert not result["score"]["preference_correct"] and not result["score"]["case_pass"]
    assert not result["score"]["false_success"]


def test_script_errors_keep_all_predeclared_denominators(tmp_path):
    m = module()
    ledger = m.open_budget(tmp_path / "budget.json", "frozen", resume=False)
    records = []
    for case in (m.load_cases()[0], m.load_cases()[5]):
        record = m.failed_record(case, m.STRATEGIES[0], "ValueError", {})
        record["run_id"] = case["id"] + "/" + m.STRATEGIES[0]
        records.append(record)
    summary = m.summarize(records, [r["run_id"] for r in records], ledger)
    metrics = summary["metrics"][m.STRATEGIES[0]]
    for key in (
        "understanding_correct",
        "goal_completed",
        "preference_correct",
        "exception_correct",
        "all_actions_verified",
    ):
        assert metrics[key] == {"numerator": 0, "denominator": 1}
    assert metrics["case_pass"] == {"numerator": 0, "denominator": 2}


def test_unknown_reading_cannot_pass_wrong_reference_or_generic_forecast_failure():
    m = module()
    case = m.load_cases()[5]
    initial = {"entities": []}
    for message in ("目标空调或窗帘与房间实际配置不一致", "预测计算暂不可用"):
        task = dict(
            status="failed",
            actions=[],
            message=message,
            agent_run=dict(failure_code="forecast_unavailable", goal={"room_id": "wrong"}),
        )
        assert not m.score(case, task, {}, None, initial, initial, False)["case_pass"]


def test_extra_nonparticipating_keep_is_not_a_goal_understanding_failure():
    m = module()
    gold = dict(
        keep_entity_ids=["required"],
        protected_room_ids=["bedroom"],
        allowed_fan_modes=["low", "auto"],
    )
    actual = {**gold, "keep_entity_ids": ["required", "unrelated_light"]}
    assert m.same_goal(actual, gold)
    actual["keep_entity_ids"] = ["unrelated_light"]
    assert not m.same_goal(actual, gold)
