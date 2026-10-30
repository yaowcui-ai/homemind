"""Separate authorized 4-run dialogue regression; never changes principal results."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import product_eval_expanded as e

BATCH = e.BATCH / "dialogue-recheck"
TARGETS = (
    ("X24", "single_forecast"),
    ("X24", "expert_forecast"),
    ("X21", "expert_forecast"),
    ("X21", "single_forecast"),
)
LIMIT = 16


def open_budget(path, fingerprint, *, parent_used, resume):
    return e.d5.d4.base.BudgetLedger(
        path,
        limit=min(LIMIT, e.LIMIT - parent_used),
        maximum=LIMIT,
        fingerprint=fingerprint,
        resume=resume,
    )


class DiagnosticModel(e.d5.d4.base.BudgetedModel):
    async def ainvoke(self, messages, tools):
        number = self.ledger.reserve(self.case_id)
        try:
            response = await self.model.ainvoke(messages, tools)
        except BaseException as error:
            record = self.ledger.data["requests"][number - 1]
            record.update(
                http_status=getattr(error, "http_status", None),
                failure_code=getattr(error, "code", "cancelled_or_deadline"),
                transport_error=getattr(error, "transport_error", None),
            )
            e.d5.d4.base.save(self.ledger.path, self.ledger.data)
            raise
        self.ledger.finish(number, response)
        return response


def hashes():
    return e.inference_hashes() | {
        p.relative_to(e.ROOT).as_posix(): e.sha(p.read_bytes().replace(b"\r\n", b"\n"))
        for p in (
            Path(__file__),
            e.ROOT / "scripts/product_eval_expanded.py",
            e.ROOT / "scripts/product_eval_d4.py",
            e.ROOT / "scripts/product_eval_d5.py",
        )
    }


def freeze():
    BATCH.mkdir(parents=True, exist_ok=True)
    parent = json.loads((e.BATCH / "budget.json").read_text(encoding="utf-8"))
    if not (e.BATCH / "stopped.json").exists():
        raise ValueError("principal_batch_must_be_stopped")
    cases = {c["id"]: c for c in e.load_cases()}
    value = dict(
        limit=LIMIT,
        total_limit=e.LIMIT,
        parent_used=parent["used"],
        parent_ledger_sha256=e.sha((e.BATCH / "budget.json").read_bytes()),
        parent_manifest_sha256=e.sha((e.BATCH / "manifest.json").read_bytes()),
        source_hashes=hashes(),
        targets=[list(x) for x in TARGETS],
        model=e.d5.MODEL,
        source_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=e.ROOT, text=True
        ).strip(),
        fixture_sha256={
            case_id: e.prepare_pair(cases[case_id])["template_sha256"] for case_id, _ in TARGETS
        },
    )
    e.d5.d4.base.write_new(BATCH / "manifest.json", value)
    return value


def validate():
    value = json.loads((BATCH / "manifest.json").read_text(encoding="utf-8"))
    if (
        value["source_hashes"] != hashes()
        or value["parent_ledger_sha256"] != e.sha((e.BATCH / "budget.json").read_bytes())
        or value["targets"] != [list(x) for x in TARGETS]
        or value["model"] != e.d5.MODEL
    ):
        raise ValueError("supplement_source_or_parent_changed")
    authorization = json.loads((BATCH / "authorization.json").read_text(encoding="utf-8"))
    if authorization.get("limit") != LIMIT or authorization.get("manifest_sha256") != e.sha(
        (BATCH / "manifest.json").read_bytes()
    ):
        raise ValueError("supplement_requires_bound_new_authorization")
    for case_id, _ in TARGETS:
        path = e.BATCH / ".fixtures" / case_id / "initial.sqlite"
        if e.sha(path.read_bytes()) != value["fixture_sha256"][case_id]:
            raise ValueError("supplement_original_initial_changed")
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
        raise ValueError("unchanged_model_configuration_required")
    lock_path = BATCH / "batch.lock"
    lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        ledger = open_budget(
            BATCH / "budget.json",
            e.sha(json.dumps(manifest, sort_keys=True).encode()),
            parent_used=manifest["parent_used"],
            resume=resume,
        )
        if (BATCH / "stopped.json").exists():
            raise ValueError("supplement_stopped")
        (BATCH / "records").mkdir(exist_ok=True)
        rows = [
            json.loads(p.read_text(encoding="utf-8")) for p in (BATCH / "records").glob("*.json")
        ]
        model = DiagnosticModel(DeepSeekModel(config), ledger)
        cases = {c["id"]: c for c in e.load_cases()}
        reason = "fixed_supplement_completed"
        for case_id, strategy in TARGETS:
            name = e.identifier("dialogue-recheck", case_id, strategy)
            if name in {r["run_id"] for r in rows}:
                continue
            if any(r["case_id"] == name for r in ledger.data["requests"]):
                raise ValueError("orphan_supplement_request_no_replay")
            needed = 5 if strategy == "expert_forecast" else 3
            if ledger.data["limit"] - ledger.used < needed:
                reason = "insufficient_supplement_headroom"
                break
            model.case_id = name
            before, capture = ledger.used, {}
            try:
                record = e.run_trial(
                    cases[case_id],
                    "dialogue-recheck",
                    strategy,
                    model,
                    source="real_model",
                    capture=capture,
                )
            except Exception as error:
                record = e.d5.d4.failed_record(
                    cases[case_id], strategy, type(error).__name__, capture
                )
                record.update(run_id=name, phase="dialogue-recheck", repetition=1)
            record["issued_requests"] = ledger.used - before
            e.d5.d4.base.write_new(BATCH / "records" / (name.replace("/", "-") + ".json"), record)
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
            failures = ledger.data["requests"][before:]
            if any(r.get("failure_code") == "model_unavailable" for r in failures):
                reason = "provider_unavailable_stop_without_retry"
                break
        e.d5.d4.base.write_new(
            BATCH / "stopped.json",
            dict(
                used=ledger.used,
                total_used=manifest["parent_used"] + ledger.used,
                total_limit=e.LIMIT,
                reason=reason,
                not_run=[
                    e.identifier("dialogue-recheck", *target)
                    for target in TARGETS
                    if e.identifier("dialogue-recheck", *target) not in {r["run_id"] for r in rows}
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
    if not (args.freeze or args.real):
        print(
            json.dumps(
                dict(status="not_run", runs=4, limit=LIMIT, total_limit=e.LIMIT, real_requests=0)
            )
        )
        return 0
    if args.freeze:
        freeze()
        print("Supplement frozen; zero model requests.")
        return 0
    return run_real(resume=args.resume)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as error:
        print("Supplement stopped: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
