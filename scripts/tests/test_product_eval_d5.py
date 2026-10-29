"""Offline D5 protocol checks; controlled replies are not language accuracy."""

import copy
import importlib.util
import inspect
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "product_eval_d5.py"
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(SCRIPT.parents[1] / "backend/src"))


def module():
    assert SCRIPT.exists(), "D5 entry point must exist"
    spec = importlib.util.spec_from_file_location("product_eval_d5", SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_explicit_new_budget_extension_preserves_original_cap():
    import product_eval as base

    assert "maximum" in inspect.signature(base.BudgetLedger).parameters


def test_default_no_configuration_or_network():
    m = module()
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == dict(
        status="not_run", cases=12, planned_runs=36, limit=120, real_requests=0
    )
    assert len(m.schedule()) == 36


def test_fixed_shared_budget_and_six_call_headroom(tmp_path):
    m = module()
    ledger = m.open_budget(tmp_path / "budget.json", "fixed", resume=False)
    for _ in range(114):
        ledger.reserve("one")
    assert m.can_start_trial(ledger)
    ledger.reserve("one")
    assert not m.can_start_trial(ledger)
    for _ in range(5):
        ledger.reserve("one")
    with pytest.raises(m.d4.base.BudgetExceeded):
        ledger.reserve("one")
    assert m.open_budget(ledger.path, "fixed", resume=True).used == 120
    with pytest.raises(FileExistsError):
        m.open_budget(ledger.path, "fixed", resume=False)
    with pytest.raises(ValueError):
        m.open_budget(ledger.path, "changed", resume=True)
    with pytest.raises(ValueError):
        m.d4.base.BudgetLedger(tmp_path / "old.json", limit=41, fingerprint="old")
    with pytest.raises(ValueError):
        m.validate_batch(tmp_path)


def test_frozen_schedule_has_twelve_new_inputs_and_preselected_repeats():
    m = module()
    cases, schedule = m.load_cases(), m.schedule()
    assert len(cases) == len({c["text"] for c in cases}) == 12
    assert sum(c["kind"] == "execute" for c in cases) == 8
    assert set(m.REPEATS) == {"A02", "A03", "A11"}
    for i in range(0, len(schedule), 2):
        pair = schedule[i : i + 2]
        assert pair[0][0:2] == pair[1][0:2]
        assert {p[2] for p in pair} == set(m.d4.STRATEGIES)
        assert pair[0][2] == m.d4.STRATEGIES[(i // 2) % 2]


class ControlledModel:
    """Case lookup deliberately supplies known answers; tests only execution wiring."""

    def __init__(self, case, suboptimal=False):
        self.case, self.suboptimal = case, suboptimal

    async def ainvoke(self, messages, tools):
        from langchain_core.messages import AIMessage

        facts, _ = json.JSONDecoder().raw_decode(
            messages[0].content.split("Frozen public context: ", 1)[1]
        )
        assert "gold" not in facts and "oracle_forecast" not in facts
        assert "expected" not in facts and "semantic_review" not in facts
        if "forecast" not in facts:
            if self.case["kind"] in {
                "missing_reading_first_response",
                "missing_priority_first_response",
            }:
                output = dict(kind="clarify", question=self.case["review_expectation"], options=[])
            else:
                output = module().gold_from_snapshot(self.case, facts["home"])
        elif not module().d4.optimal_ids(facts["forecast"], facts["goal"]["priority"]):
            output = dict(kind="clarify", question=self.case["review_expectation"], options=[])
        else:
            role = facts.get("role")
            priority = {"comfort": "comfort_first", "energy": "energy_first"}.get(
                role, facts["goal"]["priority"]
            )
            selected = module().d4.optimal_ids(facts["forecast"], priority)[0]
            if role in {"comfort", "energy"}:
                output = dict(
                    role=role,
                    outcome="recommend",
                    preferred_candidate_id=selected,
                    evidence_refs=["candidate:" + selected],
                    public_summary="受控测试回复",
                )
            else:
                if self.suboptimal:
                    selected = next(
                        c["id"]
                        for c in facts["forecast"]["candidates"]
                        if c["deadline_met"]
                        and c["id"] not in module().d4.optimal_ids(facts["forecast"], priority)
                    )
                candidate = next(c for c in facts["forecast"]["candidates"] if c["id"] == selected)
                goal = facts["goal"]
                output = dict(
                    kind="selection",
                    candidate_id=selected,
                    plan=dict(
                        kind="plan",
                        scenario="homecoming",
                        room_ids=[goal["room_id"]],
                        keep_entity_ids=goal["keep_entity_ids"],
                        protected_room_ids=goal["protected_room_ids"],
                        actions=candidate["actions"],
                        temperatures=[dict(room_id=goal["room_id"], target=26)],
                        ready_in_minutes=goal["ready_in_minutes"],
                        rationale="受控测试",
                    ),
                )
        return AIMessage(content=json.dumps(output))


@pytest.mark.parametrize("index", range(12))
def test_frozen_oracles_and_paired_exact_state(index, tmp_path):
    m = module()
    case = m.load_cases()[index]
    with m.d4.base.official_http_only():
        pair = m.prepare_pair(case, tmp_path)
        m.validate_oracle(case, pair)
        results = [
            m.run_trial(case, strategy, pair, ControlledModel(case), repetition=1)
            for strategy in m.d4.STRATEGIES
        ]
    assert results[0]["initial_snapshot"] == results[1]["initial_snapshot"]
    assert m.prepare_pair(case, tmp_path) == pair
    if case["kind"] == "execute":
        assert all(r["score"]["case_pass"] for r in results), results
        assert all(r["score"]["goal_completed"] for r in results)
        for r in results:
            selected = r["final_task"]["agent_run"]["selected_candidate_id"]
            assert r["scope_energy_wh"] == next(
                c["energy_wh"] for c in pair["forecast"]["candidates"] if c["id"] == selected
            )
    else:
        assert all(r["score"]["review_status"] == "pending" for r in results)
        assert all(not r["score"]["case_pass"] for r in results)
        for r in results:
            assert r["initial_snapshot"] == r["final_snapshot"]
            assert not r["final_task"]["actions"]
            review = m.review_binding(r) | dict(
                correct=True, reviewer="controlled test", reason=case["review_expectation"]
            )
            assert m.score_record(r, review)["case_pass"]
            review["question_sha256"] = "wrong"
            assert not m.score_record(r, review)["case_pass"]


def test_legal_preference_suboptimal_original_is_executed(tmp_path):
    m = module()
    case = m.load_cases()[0]
    with m.d4.base.official_http_only():
        pair = m.prepare_pair(case, tmp_path)
        result = m.run_trial(
            case, "single_forecast", pair, ControlledModel(case, True), repetition=1
        )
    assert result["score"]["goal_completed"]
    assert not result["score"]["preference_correct"]
    assert not result["score"]["case_pass"]


def test_all_fixtures_and_sources_frozen_before_real_and_resume_rejects_changes(tmp_path):
    m = module()
    manifest = m.freeze(tmp_path)
    assert len(manifest["fixtures"]) == 12
    assert m.validate_freeze(tmp_path) == manifest
    changed = copy.deepcopy(manifest)
    changed["model"]["name"] = "other"
    m.d4.base.save(tmp_path / "manifest.json", changed)
    with pytest.raises(ValueError):
        m.validate_freeze(tmp_path)
    m.d4.base.save(tmp_path / "manifest.json", manifest)
    fixture = tmp_path / ".fixtures/A01/initial.sqlite"
    fixture.write_bytes(fixture.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        m.validate_freeze(tmp_path)


def test_errors_and_pending_reviews_stay_in_applicable_denominators(tmp_path):
    m = module()
    ledger = m.open_budget(tmp_path / "budget.json", "fixed", resume=False)
    records = [
        m.failed_record(c, "single_forecast", 1, "ValueError", {})
        for c in (m.load_cases()[0], m.load_cases()[10])
    ]
    summary = m.summarize(records, ledger)
    metrics = summary["first_pass"]["single_forecast"]
    assert metrics["case_pass"] == dict(numerator=0, denominator=2)
    assert metrics["understanding_correct"] == dict(numerator=0, denominator=2)
    assert metrics["goal_completed"] == dict(numerator=0, denominator=1)
    assert metrics["exception_correct"] == dict(numerator=0, denominator=1)
    assert len(summary["not_run"]) == 34


def test_default_does_not_call_configuration(monkeypatch, capsys):
    m = module()

    def forbidden():
        pytest.fail("default must not load configuration")

    monkeypatch.setattr(m.d4.base, "configuration", forbidden)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT)])
    assert m.main() == 0
    assert json.loads(capsys.readouterr().out)["real_requests"] == 0


def test_resume_skips_completed_and_rejects_orphan_requests(tmp_path, monkeypatch):
    m = module()
    from homemind.agent import model as model_module

    # Narrow this orchestration test to one real API pair; all12 fixtures still freeze.
    case = m.load_cases()[0]
    planned = [(case["id"], 1, s) for s in m.d4.STRATEGIES]
    monkeypatch.setattr(m, "schedule", lambda: planned)
    monkeypatch.setattr(m, "BATCH", tmp_path)
    manifest = m.freeze(tmp_path)
    monkeypatch.setattr(
        m.d4.base,
        "configuration",
        lambda: SimpleNamespace(
            model_enabled=True,
            model_api_key=True,
            model_name=m.MODEL["name"],
            model_provider=m.MODEL["provider"],
            model_base_url=m.MODEL["base_url"],
        ),
    )
    monkeypatch.setattr(model_module, "DeepSeekModel", lambda _: ControlledModel(case))
    args = SimpleNamespace(batch=tmp_path, resume=False)
    with m.d4.base.official_http_only():
        assert m.run_real(args) == 0
        ledger_before = (tmp_path / "budget.json").read_bytes()
        args.resume = True
        assert m.run_real(args) == 0
    assert (tmp_path / "budget.json").read_bytes() == ledger_before
    records = list((tmp_path / "records").glob("A*.json"))
    assert len(records) == 2
    # A sent-but-unsaved run must stop, never silently resend the first pair.
    records[0].unlink()
    with m.d4.base.official_http_only(), pytest.raises(ValueError, match="orphan_issued"):
        m.run_real(args)
    assert (tmp_path / "budget.json").read_bytes() == ledger_before
    changed_hashes = dict(manifest["hashes"]) | {"new-source": "changed"}
    monkeypatch.setattr(m, "hashes", lambda: changed_hashes)
    with pytest.raises(ValueError, match="frozen_sources"):
        m.validate_freeze(tmp_path)


def test_review_copies_preserve_originals_and_bind_evidence(tmp_path):
    m = module()
    case = m.load_cases()[10]
    with m.d4.base.official_http_only():
        pair = m.prepare_pair(case, tmp_path / "pair")
        record = m.run_trial(case, "single_forecast", pair, ControlledModel(case), repetition=1)
    records = tmp_path / "records"
    records.mkdir()
    original = records / "A11-r1-single_forecast.json"
    m.d4.base.write_new(original, record)
    original_bytes = original.read_bytes()
    ledger = m.open_budget(tmp_path / "budget.json", "fixture", resume=False)
    budget_bytes = ledger.path.read_bytes()
    review = m.review_binding(record) | dict(
        correct=True, reviewer="controlled test author", reason=case["review_expectation"]
    )
    wrong = dict(review) | {"evidence_sha256": "wrong"}
    assert not m.score_record(record, wrong)["case_pass"]
    path = tmp_path / "reviews.json"
    m.d4.base.write_new(path, {record["run_id"]: review})
    m.audit_reviews(tmp_path, path)
    reviewed = json.loads((tmp_path / "reviewed" / original.name).read_text(encoding="utf-8"))
    assert reviewed["score"]["case_pass"]
    assert reviewed["original_score"]["review_status"] == "pending"
    assert reviewed["original_record_sha256"] == m.d4.digest(original_bytes)
    assert reviewed["semantic_review_sha256"]
    assert original.read_bytes() == original_bytes
    assert ledger.path.read_bytes() == budget_bytes
