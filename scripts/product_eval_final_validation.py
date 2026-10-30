"""Fresh V2 validation. No provider/configuration access unless --real is explicit."""

import argparse
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import product_eval_expanded as e
from product_eval_expanded_recheck import DiagnosticModel

PRINCIPAL = e.BATCH
SUPPLEMENT = PRINCIPAL / "dialogue-recheck"
BATCH = e.ROOT / "output/product-expanded-final-20261030"
CASES = e.ROOT / "evaluation/product-final-validation-cases.json"
LIMIT = 60


def load_cases():
    return json.loads(CASES.read_text(encoding="utf-8"))


def schedule():
    return [
        (case["id"], strategy)
        for i, case in enumerate(load_cases())
        for strategy in e.d5.d4.STRATEGIES[:: 1 if i % 2 == 0 else -1]
    ]


@contextmanager
def scope():
    original = e.BATCH, e.CASES
    try:
        e.BATCH, e.CASES = BATCH, CASES
        yield
    finally:
        e.BATCH, e.CASES = original


def required_requests(case, strategy):
    # No tools/retries in these goal/expert/selection stages. A reply adds one goal call.
    return (4 if strategy == "expert_forecast" else 2) + bool(case.get("reply"))


def open_budget(path, fingerprint, *, parent_used, resume):
    return e.d5.d4.base.BudgetLedger(
        path,
        limit=min(LIMIT, e.LIMIT - parent_used),
        maximum=LIMIT,
        fingerprint=fingerprint,
        resume=resume,
    )


def hashes():
    return e.inference_hashes() | {
        p.relative_to(e.ROOT).as_posix(): e.sha(p.read_bytes().replace(b"\r\n", b"\n"))
        for p in (
            Path(__file__),
            CASES,
            e.ROOT / "scripts/product_eval_expanded.py",
            e.ROOT / "scripts/product_eval_expanded_recheck.py",
            e.ROOT / "scripts/product_eval.py",
            e.ROOT / "scripts/product_eval_d4.py",
            e.ROOT / "scripts/product_eval_d5.py",
            e.ROOT / "scripts/product_eval_d4_followup.py",
        )
    }


def parents():
    paths = [p / "budget.json" for p in (PRINCIPAL, SUPPLEMENT)]
    if not all((p / "stopped.json").exists() for p in (PRINCIPAL, SUPPLEMENT)):
        raise ValueError("previous_batches_must_be_stopped")
    return dict(
        parent_used=sum(json.loads(p.read_text(encoding="utf-8"))["used"] for p in paths),
        parent_hashes={p.relative_to(e.ROOT).as_posix(): e.sha(p.read_bytes()) for p in paths},
    )


def freeze():
    BATCH.mkdir(parents=True, exist_ok=True)
    with scope():
        fixtures = {c["id"]: e.prepare_pair(c) for c in load_cases()}
    value = dict(
        **parents(),
        limit=LIMIT,
        total_limit=e.LIMIT,
        source_hashes=hashes(),
        source_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=e.ROOT, text=True
        ).strip(),
        model=e.d5.MODEL,
        cases=load_cases(),
        schedule=[list(x) for x in schedule()],
        fixtures={
            key: {
                "initial": pair["template_sha256"],
                "descriptor": e.sha((BATCH / ".fixtures" / key / "pair.json").read_bytes()),
            }
            for key, pair in fixtures.items()
        },
        limitation="same-author synthetic validation; service recovery is not prompt benefit",
    )
    e.d5.d4.base.write_new(BATCH / "manifest.json", value)
    return value


def frozen_manifest():
    return json.loads((BATCH / "manifest.json").read_text(encoding="utf-8"))


def validate():
    value = frozen_manifest()
    if value["source_hashes"] != hashes() or any(value.get(k) != v for k, v in parents().items()):
        raise ValueError("frozen_final_source_or_parent_changed")
    if (
        value["cases"] != load_cases()
        or value["schedule"] != [list(x) for x in schedule()]
        or value["model"] != e.d5.MODEL
        or value["limit"] != LIMIT
    ):
        raise ValueError("frozen_final_scope_changed")
    authorization = json.loads((BATCH / "authorization.json").read_text(encoding="utf-8"))
    if authorization.get("limit") != LIMIT or authorization.get("manifest_sha256") != e.sha(
        (BATCH / "manifest.json").read_bytes()
    ):
        raise ValueError("final_bound_authorization_required")
    for key, expected in value["fixtures"].items():
        directory = BATCH / ".fixtures" / key
        if expected != {
            "initial": e.sha((directory / "initial.sqlite").read_bytes()),
            "descriptor": e.sha((directory / "pair.json").read_bytes()),
        }:
            raise ValueError("final_fixture_or_oracle_changed")
    return value


def run_real(*, resume=False):
    sys.path.insert(0, str(e.ROOT / "backend/src"))
    from homemind.agent.model import DeepSeekModel

    manifest = validate()
    config = e.d5.d4.base.configuration()
    if (
        not config.model_enabled
        or not config.model_api_key
        or config.model_name != e.d5.MODEL["name"]
        or config.model_provider != e.d5.MODEL["provider"]
        or config.model_base_url != e.d5.MODEL["base_url"]
    ):
        raise ValueError("frozen_model_required")
    lock_path = BATCH / "batch.lock"
    lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        if (BATCH / "stopped.json").exists():
            raise ValueError("final_batch_stopped")
        ledger = open_budget(
            BATCH / "budget.json",
            e.sha(json.dumps(manifest, sort_keys=True).encode()),
            parent_used=manifest["parent_used"],
            resume=resume,
        )
        directory = BATCH / "records"
        directory.mkdir(exist_ok=True)
        rows = [json.loads(p.read_text(encoding="utf-8")) for p in directory.glob("*.json")]
        model = DiagnosticModel(DeepSeekModel(config), ledger)
        cases = {c["id"]: c for c in load_cases()}
        reason = "fixed_final_schedule_completed"
        with scope():
            for case_id, strategy in schedule():
                name = e.identifier("final-validation", case_id, strategy)
                if name in {r["run_id"] for r in rows}:
                    continue
                if any(r["case_id"] == name for r in ledger.data["requests"]):
                    raise ValueError("orphan_request_no_replay")
                if ledger.data["limit"] - ledger.used < required_requests(cases[case_id], strategy):
                    reason = "insufficient_final_headroom"
                    break
                before, capture = ledger.used, {}
                model.case_id = name
                try:
                    record = e.run_trial(
                        cases[case_id],
                        "final-validation",
                        strategy,
                        model,
                        source="real_model",
                        capture=capture,
                    )
                except Exception as error:
                    record = e.d5.d4.failed_record(
                        cases[case_id], strategy, type(error).__name__, capture
                    )
                    record.update(run_id=name, phase="final-validation", repetition=1)
                record["issued_requests"] = ledger.used - before
                e.d5.d4.base.write_new(directory / (name.replace("/", "-") + ".json"), record)
                rows.append(record)
                print(
                    json.dumps(
                        dict(
                            run_id=name,
                            status=record.get("final_task", {}).get("status"),
                            used=ledger.used,
                            total_used=manifest["parent_used"] + ledger.used,
                        )
                    ),
                    flush=True,
                )
                if record.get("error") or any(
                    r.get("failure_code") == "model_unavailable"
                    for r in ledger.data["requests"][before:]
                ):
                    reason = "provider_or_script_failure_stop_without_retry"
                    break
        e.d5.d4.base.write_new(
            BATCH / "stopped.json",
            dict(
                used=ledger.used,
                total_used=manifest["parent_used"] + ledger.used,
                total_limit=e.LIMIT,
                reason=reason,
                not_run=[
                    e.identifier("final-validation", *r)
                    for r in schedule()
                    if e.identifier("final-validation", *r) not in {x["run_id"] for x in rows}
                ],
            ),
        )
        return 0
    finally:
        os.close(lock)
        lock_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--real", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.freeze:
        freeze()
        print("Final fresh set frozen; zero model requests.")
        return 0
    if args.real:
        return run_real(resume=args.resume)
    print(json.dumps(dict(status="not_run", cases=12, runs=24, limit=LIMIT, real_requests=0)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as error:
        print("Final validation stopped: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
