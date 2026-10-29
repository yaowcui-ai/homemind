"""Three original failed strategy/case targets, new shared budget, no default HTTP."""

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import product_eval_d4 as d4

sys.path.insert(0, str(d4.ROOT / "evaluation/probes"))
import product_d4_audit as audit  # noqa: E402

BATCH = d4.ROOT / "output/product-d4-followup-20261029"
LIMIT = 24
TARGETS = (("DD01", "expert_forecast"), ("DD05", "single_forecast"), ("DD06", "expert_forecast"))


def validate_batch(path):
    if Path(path).resolve() != BATCH.resolve():
        raise ValueError("fixed_new_shared_batch_only")
    return BATCH


def open_budget(path, *, resume):
    fingerprint = d4.digest(d4.CASES.read_bytes() + json.dumps(TARGETS).encode())
    return d4.base.BudgetLedger(path, limit=LIMIT, fingerprint=fingerprint, resume=resume)


def frozen_pair(case, directory, *, source=None):
    source = source or d4.BATCH / ".fixtures" / case["id"] / "pair.json"
    pair = json.loads(Path(source).read_text(encoding="utf-8"))
    if (
        pair["case"] != case
        or d4.digest(Path(pair["template"]).read_bytes()) != pair["template_sha256"]
    ):
        raise ValueError("original_fixture_or_case_changed")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    pair["directory"] = str(directory)
    descriptor = directory / "pair.json"
    if descriptor.exists():
        if json.loads(descriptor.read_text(encoding="utf-8")) != pair:
            raise ValueError("saved_pair_changed")
    else:
        d4.base.write_new(descriptor, pair)
    return pair


def approve_plan(task, gold, forecast):
    normalized = deepcopy(task)
    run = normalized["agent_run"]
    goal = run.get("goal")
    run["goal"] = audit.canonical_goal(goal)
    if goal and goal.get("cover_constraint") == "keep" and run.get("proposed_plan"):
        plan = run["proposed_plan"]
        plan["keep_entity_ids"] = [
            i for i in plan["keep_entity_ids"] if i != goal["cover_entity_id"]
        ]
    return d4.hard_plan_matches(normalized, audit.canonical_goal(gold), forecast)


def hashes():
    return d4.source_hashes() | {
        p: d4.digest((d4.ROOT / p).read_bytes().replace(b"\r\n", b"\n"))
        for p in ("scripts/product_eval_d4_followup.py", "evaluation/probes/product_d4_audit.py")
    }


def validate_resume(prior, current, model, targets):
    if (
        prior["hashes"] != current
        or prior["model"] != model
        or prior["targets"] != [list(t) for t in targets]
    ):
        raise ValueError("resume_version_or_targets_changed")


def run_real(args):
    from homemind.agent.model import DeepSeekModel

    batch = validate_batch(args.batch)
    config = d4.base.configuration()
    if not config.model_enabled or not config.model_api_key:
        raise ValueError("model_not_configured")
    original = json.loads((d4.BATCH / "phase1/manifest.json").read_text(encoding="utf-8"))
    if config.model_name != original["model"]:
        raise ValueError("same_original_model_required")
    batch.mkdir(parents=True, exist_ok=True)
    lock_path = batch / "batch.lock"
    lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        ledger = open_budget(batch / "budget.json", resume=args.resume or bool(args.retest))
        phase = "repair" if args.retest else "diagnosis"
        current = hashes()
        targets = list(TARGETS)
        if args.retest:
            prior = json.loads((batch / "diagnosis/manifest.json").read_text(encoding="utf-8"))
            records = [
                json.loads(p.read_text(encoding="utf-8"))
                for p in (batch / "diagnosis").glob("DD*.json")
            ]
            eligible = {
                r["case_id"]
                for r in records
                if not r["score"]["case_pass"]
                and not r.get("error")
                and not r.get("needs_semantic_review")
            }
            changed = any(
                v != prior["hashes"].get(k)
                for k, v in current.items()
                if k.startswith("backend/src/homemind/agent/")
            )
            if (
                len(set(args.retest)) != len(args.retest)
                or not set(args.retest) <= eligible
                or not changed
                or prior["model"] != config.model_name
            ):
                raise ValueError("repair_needs_recorded_failure_actual_agent_change_and_same_model")
            targets = [t for t in targets if t[0] in args.retest]
        directory = batch / phase
        directory.mkdir(exist_ok=True)
        manifest = dict(
            phase=phase,
            hashes=current,
            model=config.model_name,
            targets=targets,
            limit=LIMIT,
            prior_calls=ledger.used,
            split="development",
            date="2026-10-29 Asia/Shanghai",
            thinking="disabled",
            max_tokens=2048,
            temperature="provider_default",
            source_fixture_batch=str(d4.BATCH),
            scope="three failed strategies only, not architecture comparison",
        )
        manifest_path = directory / "manifest.json"
        if args.resume:
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
            validate_resume(prior, current, config.model_name, targets)
        else:
            d4.base.write_new(manifest_path, manifest)
        records = [json.loads(p.read_text(encoding="utf-8")) for p in directory.glob("DD*.json")]
        model = d4.base.BudgetedModel(DeepSeekModel(config), ledger)
        cases = {c["id"]: c for c in d4.load_cases()}
        for case_id, strategy in targets:
            run_id = case_id + "/" + strategy
            if any(r["run_id"] == run_id for r in records):
                continue
            if LIMIT - ledger.used < 6:
                break
            model.case_id = phase + "/" + run_id
            if any(r["case_id"] == model.case_id for r in ledger.data["requests"]):
                raise ValueError("orphan_issued_request_no_automatic_replay")
            before = ledger.used
            capture = {}
            case = cases[case_id]
            try:
                pair = frozen_pair(case, batch / ".fixtures" / case_id)
                record = d4.run_trial(
                    case,
                    strategy,
                    pair,
                    model,
                    source="real_model",
                    phase=phase,
                    capture=capture,
                    approve_plan=approve_plan,
                )
                record["score_before_canonical_audit"] = record["score"]
                record["score"] = audit.audit_score(record)
                record["needs_semantic_review"] = bool(
                    case_id == "DD06" and record["final_task"]["status"] == "waiting_input"
                )
            except Exception as error:
                record = d4.failed_record(case, strategy, type(error).__name__, capture)
            record.update(
                run_id=run_id,
                issued_requests=ledger.used - before,
                shared_requests_after=ledger.used,
            )
            d4.base.write_new(directory / (case_id + "-" + strategy + ".json"), record)
            records.append(record)
            summary = dict(
                limit=LIMIT,
                shared_used=ledger.used,
                not_run=[
                    c + "/" + s
                    for c, s in targets
                    if not any(r["run_id"] == c + "/" + s for r in records)
                ],
            )
            d4.base.save(directory / "summary.json", summary)
            print(
                json.dumps(dict(run_id=run_id, score=record["score"], requests=ledger.used)),
                flush=True,
            )
            if record.get("error"):
                return 1
        d4.base.save(
            directory / "summary.json",
            dict(
                limit=LIMIT,
                shared_used=ledger.used,
                not_run=[
                    c + "/" + s
                    for c, s in targets
                    if not any(r["run_id"] == c + "/" + s for r in records)
                ],
            ),
        )
        return 0
    finally:
        os.close(lock)
        lock_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retest", nargs="+", choices=[t[0] for t in TARGETS])
    parser.add_argument("--batch", type=Path, default=BATCH)
    args = parser.parse_args()
    if not args.real:
        print(json.dumps(dict(status="not_run", targets=3, real_requests=0)))
        return 0
    try:
        with d4.base.official_http_only():
            return run_real(args)
    except Exception:
        print(json.dumps(dict(status="not_completed", reason="inspect_batch_or_configuration")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
