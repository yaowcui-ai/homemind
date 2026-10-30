"""Quality repair comparison; no config/network unless explicitly authorized --real."""

import argparse
import importlib.util
import json
import os
import statistics
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import product_eval_d5 as d5
from product_eval_d4_followup import frozen_pair

ROOT = d5.ROOT
BATCH = ROOT / "output/product-quality-real-20261030"
NEW_CASES = ROOT / "evaluation/product-quality-cases.json"
BASELINE = "53b9e3084e3a10b11554334edb196c69184c8db5"
DEVELOPMENT = ("A02", "A06", "A07", "A09", "A11", "A12")
LIMIT = 80


def load_cases():
    return [c for c in d5.load_cases() if c["id"] in DEVELOPMENT] + json.loads(
        NEW_CASES.read_text(encoding="utf-8")
    )


def schedule():
    runs = []
    for i, case in enumerate(DEVELOPMENT):
        strategies = d5.d4.STRATEGIES[:: 1 if i % 2 == 0 else -1]
        for j, strategy in enumerate(strategies):
            revisions = ("baseline", "candidate")[:: 1 if (i + j) % 2 == 0 else -1]
            runs.extend((case, revision, strategy) for revision in revisions)
    runs.extend(
        (case["id"], "candidate", strategy)
        for i, case in enumerate(load_cases())
        if case["id"] not in DEVELOPMENT
        for strategy in d5.d4.STRATEGIES[:: 1 if i % 2 == 0 else -1]
    )
    return runs


def identifier(case, revision, strategy):
    return f"{case}/{revision}/{strategy}"


def open_budget(path, fingerprint, *, resume):
    return d5.d4.base.BudgetLedger(
        path, limit=LIMIT, maximum=LIMIT, fingerprint=fingerprint, resume=resume
    )


def can_start(ledger):
    return LIMIT - ledger.used >= 6


def require_authorization(batch):
    path = Path(batch) / "authorization.json"
    if not path.exists():
        raise ValueError("new_batch_authorization_required")
    authorization = json.loads(path.read_text(encoding="utf-8"))
    if authorization.get("limit") != LIMIT or authorization.get("manifest_sha256") != d5.d4.digest(
        (Path(batch) / "manifest.json").read_bytes()
    ):
        raise ValueError("authorization_must_bind_fixed_scope_and_manifest")
    return authorization


def git_source(path):
    return subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT)


def hashes():
    result = d5.hashes()
    for path in (Path(__file__), NEW_CASES, ROOT / "scripts/tests/test_product_eval_quality.py"):
        result[path.relative_to(ROOT).as_posix()] = d5.d4.digest(
            path.read_bytes().replace(b"\r\n", b"\n")
        )
    # Only graph orchestration/prompts may differ in inference. Physics, validation,
    # schema, model parameters and execution must match the selected baseline exactly.
    changed = {"agent/graph.py", "agent/pipeline.py", "agent/prompts.py"}
    for path in sorted((ROOT / "backend/src/homemind").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if path.relative_to(ROOT / "backend/src/homemind").as_posix() in changed:
            continue
        if git_source(relative).replace(b"\r\n", b"\n") != path.read_bytes().replace(
            b"\r\n", b"\n"
        ):
            raise ValueError("comparison_requires_identical_non_prompt_inference_source")
    return result


def prepare_pair(case):
    directory = BATCH / ".fixtures" / case["id"]
    if case["id"] in DEVELOPMENT:
        return frozen_pair(
            case, directory, source=d5.BATCH / ".fixtures" / case["id"] / "pair.json"
        )
    return d5.prepare_pair(case, directory)


def freeze():
    BATCH.mkdir(parents=True, exist_ok=True)
    if (BATCH / "manifest.json").exists():
        raise FileExistsError("do_not_overwrite_frozen_quality_batch")
    pairs = {case["id"]: prepare_pair(case) for case in load_cases()}
    manifest = dict(
        date="2026-10-30",
        baseline=BASELINE,
        model=d5.MODEL,
        limit=LIMIT,
        hashes=hashes(),
        schedule=[list(run) for run in schedule()],
        cases=load_cases(),
        fixtures={
            key: dict(
                template_sha256=pair["template_sha256"],
                descriptor_sha256=d5.d4.digest(
                    (BATCH / ".fixtures" / key / "pair.json").read_bytes()
                ),
            )
            for key, pair in pairs.items()
        },
        scope="24 same-initial baseline/candidate development runs; 8 candidate-only new runs",
        new_set_limitation="same-author narrow temperature family; not an external benchmark",
    )
    d5.d4.base.write_new(BATCH / "manifest.json", manifest)
    return manifest


def validate_freeze():
    manifest = json.loads((BATCH / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest["hashes"] != hashes()
        or manifest["model"] != d5.MODEL
        or manifest["cases"] != load_cases()
        or manifest["schedule"] != [list(run) for run in schedule()]
        or manifest["baseline"] != BASELINE
        or manifest["limit"] != LIMIT
    ):
        raise ValueError("frozen_quality_source_model_or_scope_changed")
    for case in load_cases():
        pair = prepare_pair(case)
        prior = manifest["fixtures"][case["id"]]
        if (
            d5.d4.digest(Path(pair["template"]).read_bytes()) != prior["template_sha256"]
            or d5.d4.digest((BATCH / ".fixtures" / case["id"] / "pair.json").read_bytes())
            != prior["descriptor_sha256"]
        ):
            raise ValueError("frozen_quality_initial_or_oracle_changed")
        d5.validate_oracle(case, pair)
    return manifest


def load_baseline_pipeline():
    directory = BATCH / ".baseline"
    directory.mkdir(exist_ok=True)
    modules = []
    for name in ("graph", "pipeline"):
        path = directory / (name + ".py")
        raw = git_source(f"backend/src/homemind/agent/{name}.py")
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("baseline_copy_changed")
        if not path.exists():
            path.write_bytes(raw)
        spec = importlib.util.spec_from_file_location("quality_baseline_" + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    graph, pipeline = modules
    pipeline.run_planner = graph.run_planner
    pipeline.planner_graph = graph
    return pipeline.run_pipeline


@contextmanager
def revision_context(revision):
    from homemind.agent import service

    candidate = service.run_pipeline
    try:
        if revision == "baseline":
            service.run_pipeline = load_baseline_pipeline()
        yield
    finally:
        service.run_pipeline = candidate


def summarize(records, ledger):
    groups = {}
    for split in ("development", "new_cases"):
        for revision in ("baseline", "candidate"):
            for strategy in d5.d4.STRATEGIES:
                rows = [
                    r
                    for r in records
                    if r["split"] == split
                    and r["revision"] == revision
                    and r["strategy"] == strategy
                ]
                if not rows:
                    continue
                durations = [
                    r["planning_api_ms"] for r in rows if r.get("planning_api_ms") is not None
                ]
                groups[f"{split}/{revision}/{strategy}"] = dict(
                    runs=len(rows),
                    issued_requests=sum(r["issued_requests"] for r in rows),
                    planning_api_ms_median=statistics.median(durations) if durations else None,
                    metrics={
                        key: dict(
                            numerator=sum(bool(r["score"].get(key)) for r in rows),
                            denominator=sum(r["score"].get(key) is not None for r in rows),
                        )
                        for key in d5.METRICS
                    },
                )
    return dict(
        limit=LIMIT,
        issued_requests=ledger.used,
        groups=groups,
        not_run=[
            identifier(*run)
            for run in schedule()
            if identifier(*run) not in {r["run_id"] for r in records}
        ],
        script_errors=[r["run_id"] for r in records if r.get("error")],
        pending_semantic_review=[
            r["run_id"] for r in records if r["score"].get("semantic_review_required")
        ],
    )


def run_real(*, resume=False):
    sys.path.insert(0, str(ROOT / "backend/src"))
    from homemind.agent.model import DeepSeekModel

    manifest = validate_freeze()
    require_authorization(BATCH)
    config = d5.d4.base.configuration()
    if (
        not config.model_enabled
        or not config.model_api_key
        or config.model_name != d5.MODEL["name"]
        or config.model_provider != d5.MODEL["provider"]
        or config.model_base_url != d5.MODEL["base_url"]
    ):
        raise ValueError("frozen_model_configuration_required")
    lock_path = BATCH / "batch.lock"
    lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        fingerprint = d5.d4.digest(json.dumps(manifest, sort_keys=True).encode())
        ledger = open_budget(BATCH / "budget.json", fingerprint, resume=resume)
        directory = BATCH / "records"
        directory.mkdir(exist_ok=True)
        records = [
            json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))
        ]
        planned = {identifier(*run) for run in schedule()}
        if len({r["run_id"] for r in records}) != len(records) or any(
            r["run_id"] not in planned for r in records
        ):
            raise ValueError("saved_records_do_not_match_frozen_schedule")
        if (BATCH / "stopped.json").exists():
            stopped = json.loads((BATCH / "stopped.json").read_text(encoding="utf-8"))
            if stopped["used"] != ledger.used:
                raise ValueError("stopped_ledger_mismatch")
            return 0
        cases = {case["id"]: case for case in load_cases()}
        model = d5.d4.base.BudgetedModel(DeepSeekModel(config), ledger)
        for case_id, revision, strategy in schedule():
            name = identifier(case_id, revision, strategy)
            if any(r["run_id"] == name for r in records):
                continue
            if any(r["case_id"] == name for r in ledger.data["requests"]):
                raise ValueError("orphan_issued_request_no_automatic_replay")
            if not can_start(ledger):
                break
            case, before, capture = cases[case_id], ledger.used, {}
            model.case_id = name
            try:
                with revision_context(revision):
                    record = d5.d4.run_trial(
                        case,
                        strategy,
                        prepare_pair(case),
                        model,
                        source="real_model",
                        phase="quality-" + revision,
                        capture=capture,
                        approve_plan=d5.approve_plan,
                    )
                record["original_score"] = record["score"]
                record.update(repetition=1, run_id=name)
                record["score"] = d5.score_record(record, case=case)
                if case["kind"] != "execute":
                    record["review_binding"] = d5.review_binding(record)
            except Exception as error:
                record = d5.d4.failed_record(case, strategy, type(error).__name__, capture)
                record.update(repetition=1, run_id=name)
            record.update(
                revision=revision,
                split="development" if case_id in DEVELOPMENT else "new_cases",
                issued_requests=ledger.used - before,
            )
            d5.d4.base.write_new(directory / (name.replace("/", "-") + ".json"), record)
            records.append(record)
            d5.d4.base.save(BATCH / "summary.json", summarize(records, ledger))
            print(
                json.dumps(dict(run_id=name, score=record["score"], used=ledger.used)), flush=True
            )
            if record.get("error"):
                return 1
        d5.d4.base.save(BATCH / "summary.json", summarize(records, ledger))
        d5.d4.base.write_new(
            BATCH / "stopped.json",
            dict(
                used=ledger.used,
                unused=LIMIT - ledger.used,
                reason="fixed_schedule_completed_or_insufficient_round_headroom",
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
                dict(
                    status="not_run",
                    development_runs=24,
                    new_case_runs=8,
                    limit=LIMIT,
                    real_requests=0,
                )
            )
        )
        return 0
    try:
        if args.freeze:
            freeze()
            print(json.dumps(dict(status="frozen", planned_runs=32, real_requests=0)))
            return 0
        with d5.d4.base.official_http_only():
            return run_real(resume=args.resume)
    except Exception as error:
        print(json.dumps(dict(status="not_completed", error_type=type(error).__name__)))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
