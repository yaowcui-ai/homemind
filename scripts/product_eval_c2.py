"""Product C second round: 12 development cases and one shared 32-request authorization."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import product_eval as base

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evaluation/product-c2-cases.json"
BATCH = ROOT / "output/product-c2-real-20261028"
LIMIT = 32


def load_cases():
    return json.loads(CASES.read_text(encoding="utf-8"))


def validate_batch(path):
    if path.resolve() != BATCH.resolve():
        raise ValueError("this_authorization_uses_one_fixed_shared_batch")
    return path.resolve()


def open_budget(path, case_hash, *, resume):
    return base.BudgetLedger(path, limit=LIMIT, fingerprint=case_hash, resume=resume)


def select_retests(cases, records, requested):
    if not requested or len(requested) > 3 or len(set(requested)) != len(requested):
        raise ValueError("choose_one_to_three_distinct_failed_cases")
    failures = {
        r["case_id"] for r in records if r["score"]["case_pass"] is False and not r.get("error")
    }
    if not set(requested).issubset(failures):
        raise ValueError("only_recorded_phase1_failures_can_be_retested")
    return [next(c for c in cases if c["id"] == case_id) for case_id in requested]


def source_hashes():
    paths = [
        CASES,
        Path(__file__),
        Path(base.__file__),
        *sorted((ROOT / "backend/src/homemind").rglob("*.py")),
    ]
    return {
        str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in paths
    }


def validate_retest_version(first_manifest, hashes, model):
    if first_manifest["hashes"] == hashes or first_manifest["model"] != model:
        raise ValueError("retest_requires_recorded_source_change_and_same_model")


def records_in(directory):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("C*.json"))]


def run_real(args):
    sys.path.insert(0, str(ROOT / "backend/src"))
    from homemind.agent.model import DeepSeekModel

    batch = validate_batch(args.batch)
    phase = "phase2" if args.retest else "phase1"
    if args.retest and args.resume:
        raise ValueError("second_phase_is_explicit_and_not_replayed")
    config = base.configuration()
    if not config.model_enabled or not config.model_api_key:
        raise ValueError("model_not_configured")
    batch.mkdir(parents=True, exist_ok=True)
    lock_path = batch / "batch.lock"
    lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        cases = load_cases()
        ledger = open_budget(
            batch / "budget.json",
            hashlib.sha256(CASES.read_bytes()).hexdigest(),
            resume=args.resume or bool(args.retest),
        )
        hashes = source_hashes()
        if args.retest:
            if not (batch / "phase1/summary.json").is_file():
                raise ValueError("first_phase_must_have_a_saved_summary")
            first_summary = json.loads((batch / "phase1/summary.json").read_text(encoding="utf-8"))
            if first_summary["not_run"] or first_summary["script_errors"]:
                raise ValueError("first_phase_must_be_complete_without_script_errors")
            first_manifest = json.loads(
                (batch / "phase1/manifest.json").read_text(encoding="utf-8")
            )
            validate_retest_version(first_manifest, hashes, config.model_name)
            selected = select_retests(cases, records_in(batch / "phase1"), args.retest)
        else:
            selected = cases
        if ledger.used >= LIMIT:
            raise base.BudgetExceeded()
        directory = batch / phase
        directory.mkdir(exist_ok=True)
        manifest_path = directory / "manifest.json"
        if args.resume:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest["hashes"] != hashes or manifest["model"] != config.model_name:
                raise ValueError("cannot_resume_with_changed_sources_or_model")
            prior_calls = manifest["prior_calls"]
        else:
            prior_calls = ledger.used
            base.write_new(
                manifest_path,
                {
                    "date": "2026-10-28 Asia/Shanghai",
                    "phase": phase,
                    "hashes": hashes,
                    "case_order": [c["id"] for c in selected],
                    "prior_calls": prior_calls,
                    "shared_limit": LIMIT,
                    "model": config.model_name,
                    "thinking": "disabled",
                    "max_tokens": 2048,
                    "git_head": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                    ).strip(),
                    "source": "real_model_synthetic_households_isolated_sqlite",
                    "split": "development",
                    "human_wait": "scripted_immediate_answer",
                },
            )
        records = records_in(directory)
        model = base.BudgetedModel(DeepSeekModel(config), ledger)
        with tempfile.TemporaryDirectory(prefix="homemind-c2-") as temporary:
            for case in selected:
                if any(r["case_id"] == case["id"] for r in records):
                    continue
                if ledger.used >= LIMIT:
                    break
                request_case = phase + "/" + case["id"]
                if any(r["case_id"] == request_case for r in ledger.data["requests"]):
                    result = base.failed_record(case, "interrupted_no_automatic_replay")
                else:
                    model.case_id = request_case
                    before = ledger.used
                    try:
                        result = base.run_case(case, model, Path(temporary) / (case["id"] + ".db"))
                    except Exception as error:  # noqa: BLE001 - no raw provider exception text.
                        result = base.failed_record(
                            case, "evaluation_case_error", type(error).__name__
                        )
                    result["issued_requests"] = ledger.used - before
                result["phase"] = phase
                result["shared_requests_after"] = ledger.used
                base.write_new(directory / (case["id"] + ".json"), result)
                records.append(result)
                summary = base.summarize(records, ledger, selected)
                summary.update(
                    phase=phase,
                    phase_requests=ledger.used - prior_calls,
                    shared_requests=ledger.used,
                    phase_prior_calls=prior_calls,
                )
                base.save(directory / "summary.json", summary)
                print(
                    json.dumps(
                        {
                            "phase": phase,
                            "case_id": case["id"],
                            "score": result["score"],
                            "requests": ledger.used,
                        }
                    ),
                    flush=True,
                )
                if result.get("error"):
                    return 1
        summary = base.summarize(records, ledger, selected)
        summary.update(
            phase=phase,
            phase_requests=ledger.used - prior_calls,
            shared_requests=ledger.used,
            phase_prior_calls=prior_calls,
        )
        base.save(directory / "summary.json", summary)
        return 0
    finally:
        os.close(lock)
        lock_path.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retest", nargs="+")
    parser.add_argument("--batch", type=Path, default=BATCH)
    args = parser.parse_args()
    if not args.real:
        print(
            json.dumps(
                {
                    "status": "not_run",
                    "cases": len(load_cases()),
                    "new_cases": sum(
                        c["id"] not in {"C06", "C09", "C12", "C14"} for c in load_cases()
                    ),
                    "real_requests": 0,
                }
            )
        )
        return 0
    try:
        with base.official_http_only():
            return run_real(args)
    except Exception:  # noqa: BLE001 - safe CLI boundary, do not print secrets or provider body.
        print(json.dumps({"status": "not_completed", "reason": "check_batch_state_or_config"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
