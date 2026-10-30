"""Frozen expanded development/validation; default never reads credentials or calls models."""

import argparse
import importlib.util
import json
import os
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import product_eval_d5 as d5

ROOT = d5.ROOT
BATCH = ROOT / "output/product-expanded-real-20261030"
CASES = ROOT / "evaluation/product-expanded-cases.json"
BASELINE = "491df1fa31d910d43ff56e14d09ff3e9c7a6933f"
LIMIT = 360
PROMPT_FILES = {"agent/prompts.py", "agent/graph.py", "agent/pipeline.py"}
PHASES = ("baseline", "candidate", "holdout")


def load_cases():
    return json.loads(CASES.read_text(encoding="utf-8"))


def schedule():
    return [
        (phase, case["id"], strategy)
        for phase in PHASES
        for i, case in enumerate(load_cases())
        if case["split"] == ("holdout" if phase == "holdout" else "development")
        for strategy in d5.d4.STRATEGIES[:: 1 if i % 2 == 0 else -1]
    ]


def identifier(phase, case_id, strategy):
    return f"{phase}/{case_id}/{strategy}"


def open_budget(path, fingerprint, *, resume):
    return d5.d4.base.BudgetLedger(
        path, limit=LIMIT, maximum=LIMIT, fingerprint=fingerprint, resume=resume
    )


def can_start(ledger, case):
    return LIMIT - ledger.used >= (12 if case.get("reply") else 6)


def git_source(relative):
    return subprocess.check_output(["git", "show", f"{BASELINE}:{relative}"], cwd=ROOT)


def sha(data):
    return d5.d4.digest(data)


def hashes():
    paths = [
        Path(__file__),
        CASES,
        ROOT / "scripts/product_eval.py",
        ROOT / "scripts/product_eval_d4.py",
        ROOT / "scripts/product_eval_d5.py",
        ROOT / "scripts/product_eval_d4_followup.py",
        ROOT / "evaluation/probes/product_d4_audit.py",
    ]
    return {
        p.relative_to(ROOT).as_posix(): sha(p.read_bytes().replace(b"\r\n", b"\n")) for p in paths
    }


def inference_hashes():
    return {
        p.relative_to(ROOT).as_posix(): sha(p.read_bytes().replace(b"\r\n", b"\n"))
        for p in sorted((ROOT / "backend/src/homemind").rglob("*.py"))
    }


def check_common_source():
    for p in sorted((ROOT / "backend/src/homemind").rglob("*.py")):
        if p.relative_to(ROOT / "backend/src/homemind").as_posix() in PROMPT_FILES:
            continue
        if p.read_bytes().replace(b"\r\n", b"\n") != git_source(
            p.relative_to(ROOT).as_posix()
        ).replace(b"\r\n", b"\n"):
            raise ValueError("non_prompt_inference_source_must_match_baseline")


def fixture_setup(case, client, devices, room_id):
    if case.get("missing") == "window":
        d5.d4.base.checked(
            client.post("/simulation/events", json={"entity_id": devices["window"], "known": False})
        )
    if case.get("other_room_unknown"):
        snapshot = d5.d4.base.checked(client.get("/simulation"))
        other = next(
            e for e in snapshot["entities"] if e["room_id"] != room_id and e["type"] == "occupancy"
        )
        d5.d4.base.checked(
            client.post("/simulation/events", json={"entity_id": other["id"], "known": False})
        )


def prepare_pair(case):
    return d5.prepare_pair(
        case,
        BATCH / ".fixtures" / case["id"],
        setup=lambda client, devices, room_id: fixture_setup(case, client, devices, room_id),
    )


def freeze():
    BATCH.mkdir(parents=True, exist_ok=True)
    if (BATCH / "manifest.json").exists():
        raise FileExistsError("frozen_batch_must_not_be_overwritten")
    check_common_source()
    pairs = {c["id"]: prepare_pair(c) for c in load_cases()}
    manifest = dict(
        date="2026-10-30",
        baseline=BASELINE,
        limit=LIMIT,
        model=d5.MODEL,
        cases=load_cases(),
        schedule=[list(r) for r in schedule()],
        protocol_hashes=hashes(),
        baseline_source=inference_hashes(),
        fixtures={
            k: dict(
                template_sha256=p["template_sha256"],
                descriptor_sha256=sha((BATCH / ".fixtures" / k / "pair.json").read_bytes()),
            )
            for k, p in pairs.items()
        },
        limitation="same-author synthetic scenarios; phase timing not randomized across revisions",
    )
    d5.d4.base.write_new(BATCH / "manifest.json", manifest)
    return manifest


def validate_freeze():
    manifest = json.loads((BATCH / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest["protocol_hashes"] != hashes()
        or manifest["cases"] != load_cases()
        or manifest["schedule"] != [list(r) for r in schedule()]
        or manifest["model"] != d5.MODEL
        or manifest["baseline"] != BASELINE
        or manifest["limit"] != LIMIT
    ):
        raise ValueError("frozen_protocol_cases_model_or_scope_changed")
    check_common_source()
    for case in load_cases():
        pair = prepare_pair(case)
        expected = manifest["fixtures"][case["id"]]
        if (
            sha(Path(pair["template"]).read_bytes()) != expected["template_sha256"]
            or sha((BATCH / ".fixtures" / case["id"] / "pair.json").read_bytes())
            != expected["descriptor_sha256"]
        ):
            raise ValueError("frozen_fixture_or_oracle_changed")
    return manifest


def require_authorization(batch):
    path = Path(batch) / "authorization.json"
    if not path.exists():
        raise ValueError("new_batch_authorization_required")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("limit") != LIMIT or value.get("manifest_sha256") != sha(
        (Path(batch) / "manifest.json").read_bytes()
    ):
        raise ValueError("authorization_must_bind_limit_and_manifest")
    return value


def load_baseline_pipeline():
    directory = BATCH / ".baseline"
    directory.mkdir(exist_ok=True)
    modules = {}
    from homemind.agent import prompts

    try:
        for name in ("prompts", "graph", "pipeline"):
            path = directory / (name + ".py")
            raw = git_source(f"backend/src/homemind/agent/{name}.py")
            if path.exists() and path.read_bytes() != raw:
                raise ValueError("baseline_copy_changed")
            if not path.exists():
                path.write_bytes(raw)
            spec = importlib.util.spec_from_file_location("expanded_baseline_" + name, path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            modules[name] = module
            if name == "prompts":
                sys.modules["homemind.agent.prompts"] = module
        modules["pipeline"].run_planner = modules["graph"].run_planner
        modules["pipeline"].planner_graph = modules["graph"]
        return modules["pipeline"].run_pipeline
    finally:
        sys.modules["homemind.agent.prompts"] = prompts


@contextmanager
def revision_context(phase):
    from homemind.agent import service

    candidate = service.run_pipeline
    try:
        if phase == "baseline":
            service.run_pipeline = load_baseline_pipeline()
        yield
    finally:
        service.run_pipeline = candidate


def scripted_reply(case, client, task):
    history = dict(
        first_snapshot=d5.d4.base.checked(client.get("/simulation")),
        reply=case["reply"],
        replied=False,
    )
    if task["status"] != "waiting_input":
        return task, 0, history
    started = time.monotonic()
    final = d5.d4.base.checked(
        client.post(
            f"/tasks/{task['id']}/reply",
            json={"text": case["reply"], "expected_turn": task["agent_run"]["turn"]},
            headers={"Idempotency-Key": "expanded-reply-" + uuid4().hex},
        )
    )
    history["replied"] = True
    history["reply_task"] = final
    return final, round((time.monotonic() - started) * 1000), history


def review_binding(record, case):
    if not case.get("reply"):
        return d5.review_binding(record)
    question = (record["first_task"].get("agent_run") or {}).get("question") or ""
    evidence = {
        k: record[k]
        for k in (
            "case_id",
            "strategy",
            "text",
            "first_task",
            "journey",
            "final_task",
            "initial_snapshot",
            "final_snapshot",
        )
    }
    return dict(
        question_sha256=sha(question.encode()),
        evidence_sha256=sha(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()),
    )


def score_record(record, case, review=None):
    score = d5.score_record(record, review=review, case=case)
    if case.get("reply"):
        first = record["first_task"]
        journey = record.get("journey") or {}
        run = first.get("agent_run") or {}
        structural = bool(
            first["status"] == "waiting_input"
            and run.get("question")
            and run.get("options") == []
            and not first.get("actions")
            and journey.get("replied")
            and journey.get("first_snapshot") == record["initial_snapshot"]
        )
        binding = review_binding(record, case)
        accepted = bool(
            review
            and review.get("correct") is True
            and review.get("reviewer")
            and review.get("reason")
            and all(review.get(k) == value for k, value in binding.items())
        )
        score.update(
            structural_exception_correct=structural,
            exception_correct=structural and accepted,
            semantic_review_required=True,
            review_status="accepted" if accepted else "rejected" if review else "pending",
        )
        score["journey_completed"] = bool(score["case_pass"] and structural and accepted)
        score["case_pass"] = score["journey_completed"]
        score["understanding_correct"] = bool(
            score["understanding_correct"] and structural and accepted
        )
    elif case["kind"] == "execute":
        score["journey_completed"] = None
    elif review and not review.get("correct"):
        score["review_status"] = "rejected"
    return score


def run_trial(case, phase, strategy, model, *, source="controlled_test", capture=None):
    pair = prepare_pair(case)
    record = d5.d4.run_trial(
        case,
        strategy,
        pair,
        model,
        source=source,
        phase="expanded-" + phase,
        capture=capture,
        approve_plan=d5.approve_plan,
        follow_up=(lambda client, task: scripted_reply(case, client, task))
        if case.get("reply")
        else None,
    )
    record.update(
        repetition=1,
        run_id=identifier(phase, case["id"], strategy),
        phase=phase,
        family=case["family"],
        split=case["split"],
    )
    record["original_score"] = record["score"]
    record["score"] = score_record(record, case)
    if case.get("reply") or case["kind"] != "execute":
        record["review_binding"] = review_binding(record, case)
    return record


def records():
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((BATCH / "records").glob("*.json"))
    ]


def summarize(rows, ledger):
    groups = {}
    for phase in PHASES:
        for strategy in d5.d4.STRATEGIES:
            group = [r for r in rows if r["phase"] == phase and r["strategy"] == strategy]
            if not group:
                continue
            durations = [
                r["planning_api_ms"] for r in group if r.get("planning_api_ms") is not None
            ]
            groups[f"{phase}/{strategy}"] = dict(
                runs=len(group),
                issued_requests=sum(r["issued_requests"] for r in group),
                planning_api_ms_median=statistics.median(durations) if durations else None,
                metrics={
                    key: dict(
                        numerator=sum(bool(r["score"].get(key)) for r in group),
                        denominator=sum(r["score"].get(key) is not None for r in group),
                    )
                    for key in (*d5.METRICS, "journey_completed")
                },
            )
    return dict(
        limit=LIMIT,
        issued_requests=ledger.used,
        groups=groups,
        not_run=[
            identifier(*r) for r in schedule() if identifier(*r) not in {s["run_id"] for s in rows}
        ],
        pending_semantic_review=[
            r["run_id"]
            for r in rows
            if r["score"].get("semantic_review_required")
            and r["score"].get("review_status") == "pending"
        ],
        script_errors=[r["run_id"] for r in rows if r.get("error")],
    )


def freeze_candidate():
    validate_freeze()
    if not (BATCH / "baseline-complete.json").exists():
        raise ValueError("baseline_phase_must_complete_first")
    value = dict(
        source_hashes=inference_hashes(),
        protocol_hashes=hashes(),
        commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    )
    d5.d4.base.write_new(BATCH / "candidate.json", value)
    return value


def validate_phase(phase, manifest):
    if phase == "baseline":
        if inference_hashes() != manifest["baseline_source"]:
            raise ValueError("baseline_source_changed_before_development")
    else:
        candidate = json.loads((BATCH / "candidate.json").read_text(encoding="utf-8"))
        if (
            candidate["source_hashes"] != inference_hashes()
            or candidate["protocol_hashes"] != hashes()
        ):
            raise ValueError("candidate_changed_after_freeze")
        if phase == "holdout" and not (BATCH / "candidate-complete.json").exists():
            raise ValueError("candidate_development_must_complete_before_holdout")


def run_real(phase, *, resume=False):
    sys.path.insert(0, str(ROOT / "backend/src"))
    from homemind.agent.model import DeepSeekModel

    manifest = validate_freeze()
    require_authorization(BATCH)
    validate_phase(phase, manifest)
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
        ledger = open_budget(
            BATCH / "budget.json", sha(json.dumps(manifest, sort_keys=True).encode()), resume=resume
        )
        directory = BATCH / "records"
        directory.mkdir(exist_ok=True)
        prior = records()
        planned = {identifier(*r) for r in schedule()}
        if len({r["run_id"] for r in prior}) != len(prior) or any(
            r["run_id"] not in planned for r in prior
        ):
            raise ValueError("records_do_not_match_frozen_schedule")
        if (BATCH / "stopped.json").exists():
            raise ValueError("batch_is_stopped")
        model = d5.d4.base.BudgetedModel(DeepSeekModel(config), ledger)
        cases = {c["id"]: c for c in load_cases()}
        phase_complete = True
        for selected, case_id, strategy in schedule():
            if selected != phase:
                continue
            name = identifier(selected, case_id, strategy)
            if name in {r["run_id"] for r in prior}:
                continue
            if any(r["case_id"] == name for r in ledger.data["requests"]):
                raise ValueError("orphan_request_no_automatic_replay")
            case = cases[case_id]
            if not can_start(ledger, case):
                phase_complete = False
                break
            before, capture = ledger.used, {}
            model.case_id = name
            try:
                with revision_context(phase):
                    record = run_trial(
                        case, phase, strategy, model, source="real_model", capture=capture
                    )
            except Exception as error:
                record = d5.d4.failed_record(case, strategy, type(error).__name__, capture)
                record.update(
                    repetition=1,
                    run_id=name,
                    phase=phase,
                    family=case["family"],
                    split=case["split"],
                )
            record["issued_requests"] = ledger.used - before
            d5.d4.base.write_new(directory / (name.replace("/", "-") + ".json"), record)
            prior.append(record)
            d5.d4.base.save(BATCH / "summary.json", summarize(prior, ledger))
            print(
                json.dumps(
                    dict(
                        run_id=name,
                        status=record.get("final_task", {}).get("status"),
                        failure=(record.get("final_task", {}).get("agent_run") or {}).get(
                            "failure_code"
                        ),
                        used=ledger.used,
                    )
                ),
                flush=True,
            )
            if record.get("error"):
                return 1
        if phase_complete:
            d5.d4.base.write_new(
                BATCH / (phase + "-complete.json"), dict(phase=phase, used=ledger.used)
            )
        if not phase_complete or phase == "holdout":
            d5.d4.base.write_new(
                BATCH / "stopped.json",
                dict(
                    used=ledger.used,
                    unused=LIMIT - ledger.used,
                    reason="fixed_schedule_completed"
                    if phase_complete
                    else "insufficient_round_headroom",
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
    mode.add_argument("--freeze-candidate", action="store_true")
    mode.add_argument("--real", action="store_true")
    parser.add_argument("--phase", choices=PHASES, default="baseline")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not (args.freeze or args.freeze_candidate or args.real):
        print(
            json.dumps(
                dict(
                    status="not_run",
                    development_cases=24,
                    holdout_cases=12,
                    planned_runs=120,
                    limit=LIMIT,
                    real_requests=0,
                )
            )
        )
        return 0
    sys.path.insert(0, str(ROOT / "backend/src"))
    if args.freeze:
        freeze()
        print("Expanded cases, exact fixtures, oracles and source frozen; zero model requests.")
        return 0
    if args.freeze_candidate:
        freeze_candidate()
        print("Candidate source frozen; zero model requests.")
        return 0
    return run_real(args.phase, resume=args.resume)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as error:
        print("Expanded evaluation stopped: " + type(error).__name__, file=sys.stderr)
        raise SystemExit(1) from None
