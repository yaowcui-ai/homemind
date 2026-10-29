"""Separate D4 oracle audit; never overwrite or replay an original model request."""

import argparse
import json
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend/src"))
import product_eval_d4 as d4  # noqa: E402


def canonical_goal(goal):
    value = deepcopy(goal)
    if value and value.get("cover_constraint") == "keep":
        value["keep_entity_ids"] = [
            i for i in value["keep_entity_ids"] if i != value["cover_entity_id"]
        ]
    return value


def audit_score(record, review=None):
    task = deepcopy(record["final_task"])
    run = task.get("agent_run") or {}
    goal = run.get("goal")
    run["goal"] = canonical_goal(goal)
    if goal and goal.get("cover_constraint") == "keep" and run.get("proposed_plan"):
        plan = run["proposed_plan"]
        plan["keep_entity_ids"] = [
            i for i in plan["keep_entity_ids"] if i != goal["cover_entity_id"]
        ]
    case = next(c for c in d4.load_cases() if c["id"] == record["case_id"])
    result = d4.score(
        case,
        task,
        canonical_goal(record["gold"]),
        record["oracle_forecast"],
        record["initial_snapshot"],
        record["final_snapshot"],
        record["score"]["confirmation_observed"],
    )
    if case["kind"] == "unknown_reading_first_response" and task["status"] == "waiting_input":
        question = run.get("question")
        accepted = bool(
            review
            and review.get("correct") is True
            and question
            and review.get("question_sha256") == d4.digest(question.encode())
            and review.get("reviewer")
            and review.get("reason")
            and run.get("options") == []
            and not task.get("actions")
            and record["initial_snapshot"] == record["final_snapshot"]
        )
        result.update(
            exception_correct=accepted,
            case_pass=accepted,
            semantic_review_required=True,
            semantic_review_accepted=accepted,
        )
    return result


def continue_saved_trial(record, pair):
    """Only finish the already-produced DD05/M plan. Model is disabled in this app."""
    from homemind.simulation.physics import energy_wh

    if record["case_id"] != "DD05" or record["strategy"] != "expert_forecast":
        raise ValueError("only_recorded_guard_false_rejection_is_allowed")
    trial = Path(pair["directory"]) / "phase1-expert_forecast.sqlite"
    with d4.trial_client(trial, pair["username"]) as client:
        task = d4.base.checked(client.get("/tasks/" + record["final_task"]["id"]))
        initial = d4.base.checked(client.get("/simulation"))
        if (
            task["status"] != "waiting_confirmation"
            or task["actions"]
            or initial != record["initial_snapshot"]
        ):
            raise ValueError("original_unexecuted_task_and_initial_facts_required")
        normalized = deepcopy(task)
        normalized["agent_run"]["goal"] = canonical_goal(normalized["agent_run"]["goal"])
        if not d4.hard_plan_matches(normalized, canonical_goal(pair["gold"]), pair["forecast"]):
            raise ValueError("original_plan_must_meet_actual_requirements")
        task = d4.base.checked(
            client.post(
                "/tasks/" + task["id"] + "/confirm",
                json={"expected_turn": task["agent_run"]["turn"]},
                headers={"Idempotency-Key": "d4-dd05-guard-audit-confirm"},
            )
        )
        now = d4.base.checked(client.get("/simulation"))
        task = d4.base.checked(
            client.post(
                "/tasks/" + task["id"] + "/advance",
                json={
                    "expected_world_id": now["world_id"],
                    "expected_simulated_minutes": now["simulated_minutes"],
                },
                headers={"Idempotency-Key": "d4-dd05-guard-audit-advance"},
            )
        )
        final = d4.base.checked(client.get("/simulation"))

        async def scope_energy():
            async with client.app.state.database.home(initial["home_id"], save=False) as (
                _,
                _,
                engine,
            ):
                total = sum(
                    (
                        engine._entities[i].energy_watt_minutes
                        for i in (
                            pair["gold"]["climate_entity_id"],
                            pair["gold"]["cover_entity_id"],
                        )
                    ),
                    Decimal(0),
                )
                return energy_wh(total - Decimal(pair["scope_initial_watt_minutes"]))

        result = deepcopy(record)
        result.update(
            final_task=task,
            final_snapshot=final,
            scope_energy_wh=client.portal.call(scope_energy),
            continuation_note=(
                "Original task confirmed after guard oracle correction; no new model calls"
            ),
            continuation_model_requests=0,
            original_uncontinued_elapsed_ms=record["elapsed_ms"],
        )
        # Do not invent a comparable total elapsed time across a paused audit interval.
        result["elapsed_ms"] = None
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--continue-dd05", action="store_true")
    args = parser.parse_args()
    if not args.audit:
        print(json.dumps({"status": "not_run", "real_requests": 0}))
        return 0
    batch = d4.BATCH
    ledger_before = (batch / "budget.json").read_bytes()
    reviews_path = batch / "semantic-reviews.json"
    reviews = json.loads(reviews_path.read_text(encoding="utf-8")) if reviews_path.exists() else {}
    target = batch / "audit-v2"
    target.mkdir(exist_ok=True)
    with d4.base.official_http_only():
        for path in sorted((batch / "phase1").glob("DD*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            if args.continue_dd05 and record["run_id"] == "DD05/expert_forecast":
                pair = json.loads((batch / ".fixtures/DD05/pair.json").read_text(encoding="utf-8"))
                record = continue_saved_trial(record, pair)
            record["original_record_sha256"] = d4.digest(path.read_bytes())
            record["original_score"] = deepcopy(record["score"])
            record["score"] = audit_score(record, reviews.get(record["run_id"]))
            record["audit_version"] = "v2_cover_equivalence_and_explicit_semantic_review"
            d4.base.write_new(target / path.name, record)
    assert (batch / "budget.json").read_bytes() == ledger_before, "audit_must_not_spend_requests"
    print(json.dumps({"audited_records": 12, "additional_model_requests": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
