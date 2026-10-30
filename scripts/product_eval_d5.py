"""Frozen D5 acceptance. Default is offline; --freeze precedes opt-in --real."""

import argparse
import json
import os
import sys
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import product_eval_d4 as d4
from product_eval_d4_followup import approve_plan

ROOT = d4.ROOT
CASES = ROOT / "evaluation/product-d5-cases.json"
BATCH = ROOT / "output/product-d5-real-20261029"
LIMIT = 120
REPEATS = ("A02", "A03", "A11")
MODEL = dict(
    name="deepseek-flash",
    provider="deepseek",
    base_url="https://api.deepseek.com",
    thinking="disabled",
    max_tokens=2048,
    temperature="provider_default",
    retries=0,
)
METRICS = (
    "case_pass",
    "understanding_correct",
    "goal_completed",
    "preference_correct",
    "exception_correct",
    "all_actions_verified",
)


def load_cases():
    return json.loads(CASES.read_text(encoding="utf-8"))


def schedule():
    pairs = [(c["id"], 1) for c in load_cases()]
    pairs += [(case_id, repeat) for repeat in (2, 3) for case_id in REPEATS]
    return [
        (case_id, repeat, strategy)
        for i, (case_id, repeat) in enumerate(pairs)
        for strategy in d4.STRATEGIES[:: 1 if i % 2 == 0 else -1]
    ]


def run_id(case_id, repetition, strategy):
    return f"{case_id}/r{repetition}/{strategy}"


def validate_batch(path):
    if Path(path).resolve() != BATCH.resolve():
        raise ValueError("one_fixed_new_shared_batch_only")
    return BATCH


def open_budget(path, fingerprint, *, resume):
    return d4.base.BudgetLedger(
        path, limit=LIMIT, maximum=LIMIT, fingerprint=fingerprint, resume=resume
    )


def can_start_trial(ledger):
    return LIMIT - ledger.used >= 6


def gold_from_snapshot(case, snapshot):
    rooms = {r["name"]: r["id"] for r in snapshot["rooms"]}
    room_id = rooms[case["room"]]
    entities = {e["type"]: e["id"] for e in snapshot["entities"] if e["room_id"] == room_id}
    return dict(
        kind="goal",
        room_id=room_id,
        climate_entity_id=entities["climate"],
        cover_entity_id=entities["cover"],
        target_temperature_c=26,
        ready_in_minutes=case["minutes"],
        priority=case["priority"],
        allowed_fan_modes=case["fans"],
        cover_constraint=case["cover"],
        keep_entity_ids=[entities["light"]],
        protected_room_ids=[i for i in rooms.values() if i != room_id],
    )


def prepare_pair(case, directory):
    """Private exact SQLite template and oracle; neither is given to the model."""
    sys.path.insert(0, str(ROOT / "backend/src"))
    from homemind.agent.forecast import forecast_plan
    from homemind.simulation.models import SimulationError

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    descriptor = directory / "pair.json"
    if descriptor.exists():
        pair = json.loads(descriptor.read_text(encoding="utf-8"))
        if (
            pair["case"] != case
            or d4.digest(Path(pair["template"]).read_bytes()) != pair["template_sha256"]
        ):
            raise ValueError("frozen_fixture_changed")
        return pair
    template = directory / "initial.sqlite"
    if template.exists():
        raise ValueError("partial_fixture_requires_inspection_not_reset")
    with d4.base.synthetic_client(template) as client:
        initial = d4.base.checked(client.get("/simulation"))
        slot = "客厅" if case["target_slot"] == "living" else "卧室"
        room_id = next(r["id"] for r in initial["rooms"] if r["name"] == slot)
        d4.base.checked(client.patch("/simulation/rooms/" + room_id, json={"name": case["room"]}))
        devices = {e["type"]: e["id"] for e in initial["entities"] if e["room_id"] == room_id}
        for entity in initial["entities"]:
            if entity["room_id"] == room_id:
                d4.base.checked(
                    client.patch(
                        "/simulation/entities/" + entity["id"],
                        json={"name": case["room"] + entity["name"].removeprefix(slot)},
                    )
                )
            if entity["type"] == "light":
                d4.base.checked(
                    client.post(
                        "/simulation/controls/" + entity["id"],
                        json=dict(
                            action="set_light",
                            parameters={
                                "brightness_pct": 37 if entity["room_id"] == room_id else 65
                            },
                        ),
                    )
                )
        for kind, field, value in (
            ("temperature", "temperature_c", case["temperature"]),
            ("occupancy", "occupied", case["occupied"]),
        ):
            d4.base.checked(
                client.post("/simulation/events", json={"entity_id": devices[kind], field: value})
            )
        for kind, action, parameters in (
            ("cover", "set_cover", {"position_pct": case["cover_position"]}),
            (
                "climate",
                "set_climate",
                {"mode": "off", "fan_mode": case["initial_fan"], "target_temperature_c": 28},
            ),
        ):
            d4.base.checked(
                client.post(
                    "/simulation/controls/" + devices[kind],
                    json=dict(action=action, parameters=parameters),
                )
            )
        if case.get("missing") == "main_temperature":
            d4.base.checked(
                client.post(
                    "/simulation/events", json={"entity_id": devices["temperature"], "known": False}
                )
            )
        if case.get("missing") == "secondary_occupancy":
            added = d4.base.checked(
                client.post(
                    "/simulation/entities",
                    json=dict(
                        room_id=room_id, name=case["room"] + "角落辅助存在", type="occupancy"
                    ),
                )
            )
            secondary = next(
                e["id"] for e in added["entities"] if e["name"] == case["room"] + "角落辅助存在"
            )
            d4.base.checked(
                client.post("/simulation/events", json={"entity_id": secondary, "known": False})
            )
        initial = d4.base.checked(client.get("/simulation"))
        gold = gold_from_snapshot(case, initial)
        username = d4.base.checked(client.get("/auth/session"))["user"]["username"]

        async def oracle():
            async with client.app.state.database.home(initial["home_id"], save=False) as (
                _,
                _,
                engine,
            ):
                baseline = str(
                    sum(
                        (
                            engine._entities[i].energy_watt_minutes
                            for i in (gold["climate_entity_id"], gold["cover_entity_id"])
                        ),
                        Decimal(0),
                    )
                )
                if case["kind"] == "missing_priority_first_response":
                    return None, "priority_missing", baseline, None
                try:
                    return forecast_plan(engine, gold), None, baseline, None
                except SimulationError as error:
                    return None, error.code, baseline, error.message

        forecast, failure, baseline, message = client.portal.call(oracle)
    pair = dict(
        case=case,
        template=str(template),
        template_sha256=d4.digest(template.read_bytes()),
        username=username,
        gold=gold,
        forecast=forecast,
        oracle_failure=failure,
        oracle_message=message,
        scope_initial_watt_minutes=baseline,
        initial_snapshot=initial,
        directory=str(directory),
    )
    validate_oracle(case, pair)
    d4.base.write_new(descriptor, pair)
    return pair


def validate_oracle(case, pair):
    feasible = d4.optimal_ids(pair["forecast"], case["priority"]) if pair["forecast"] else []
    valid = (
        bool(feasible)
        if case["kind"] == "execute"
        else bool(pair["forecast"] and not feasible)
        if case["kind"] == "infeasible_first_response"
        else pair["oracle_failure"] == "priority_missing"
        if case["kind"] == "missing_priority_first_response"
        else pair["oracle_failure"] == "forecast_unavailable"
        and pair["oracle_message"] == case["expected_oracle_error"]
    )
    if not valid:
        raise ValueError("predeclared_case_oracle_mismatch_" + case["id"])


def hashes():
    paths = (
        CASES,
        Path(__file__),
        ROOT / "scripts/product_eval_d4_followup.py",
        ROOT / "evaluation/probes/product_d4_audit.py",
        ROOT / "scripts/tests/test_product_eval_d5.py",
    )
    return d4.source_hashes() | {
        p.relative_to(ROOT).as_posix(): d4.digest(p.read_bytes().replace(b"\r\n", b"\n"))
        for p in paths
    }


def freeze(batch):
    """Materialize ALL cases, expected oracles and snapshots before any model call."""
    batch = Path(batch)
    batch.mkdir(parents=True, exist_ok=True)
    if (batch / "manifest.json").exists():
        raise FileExistsError("do_not_replace_frozen_manifest")
    if (batch / "budget.json").exists():
        raise ValueError("no_new_freeze_after_requests")
    fixtures = {}
    for case in load_cases():
        directory = batch / ".fixtures" / case["id"]
        pair = prepare_pair(case, directory)
        fixtures[case["id"]] = dict(
            template_sha256=pair["template_sha256"],
            descriptor_sha256=d4.digest((directory / "pair.json").read_bytes()),
            optimal_ids=d4.optimal_ids(pair["forecast"], case["priority"])
            if pair["forecast"]
            else [],
        )
    manifest = dict(
        version="d5-v1",
        split="acceptance_new_at_freeze_same_author",
        hashes=hashes(),
        model=MODEL,
        schedule=schedule(),
        limit=LIMIT,
        fixtures=fixtures,
        date="2026-10-29 Asia/Shanghai",
        scope="E single-round; exceptions first-response only",
        authorization="freeze is offline; real requests require separate new120 authorization",
    )
    d4.base.write_new(batch / "manifest.json", manifest)
    return json.loads((batch / "manifest.json").read_text(encoding="utf-8"))


def validate_freeze(batch):
    batch = Path(batch)
    manifest = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
    if (
        manifest["hashes"] != hashes()
        or manifest["model"] != MODEL
        or manifest["limit"] != LIMIT
        or manifest["schedule"] != [list(t) for t in schedule()]
    ):
        raise ValueError("frozen_sources_model_or_schedule_changed")
    if set(manifest["fixtures"]) != {c["id"] for c in load_cases()}:
        raise ValueError("all_twelve_fixtures_required_before_first_request")
    for case in load_cases():
        directory = batch / ".fixtures" / case["id"]
        frozen = manifest["fixtures"][case["id"]]
        if (
            d4.digest((directory / "pair.json").read_bytes()) != frozen["descriptor_sha256"]
            or d4.digest((directory / "initial.sqlite").read_bytes()) != frozen["template_sha256"]
        ):
            raise ValueError("frozen_initial_or_oracle_changed")
        validate_oracle(case, prepare_pair(case, directory))
    return manifest


def review_binding(record):
    task = record["final_task"]
    question = (task.get("agent_run") or {}).get("question") or task.get("message") or ""
    evidence = {
        k: record[k]
        for k in (
            "case_id",
            "strategy",
            "repetition",
            "text",
            "initial_snapshot",
            "final_task",
            "final_snapshot",
        )
    }
    return dict(
        question_sha256=d4.digest(question.encode()),
        evidence_sha256=d4.digest(
            json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()
        ),
    )


def score_record(record, review=None, *, case=None):
    case = case or next(c for c in load_cases() if c["id"] == record["case_id"])
    if case["kind"] == "execute":
        normalized = deepcopy(record["final_task"])
        run = normalized.get("agent_run") or {}
        from product_eval_d4_followup import audit

        goal = run.get("goal")
        run["goal"] = audit.canonical_goal(goal)
        if goal and goal.get("cover_constraint") == "keep" and run.get("proposed_plan"):
            run["proposed_plan"]["keep_entity_ids"] = [
                i for i in run["proposed_plan"]["keep_entity_ids"] if i != goal["cover_entity_id"]
            ]
        return d4.score(
            case,
            normalized,
            audit.canonical_goal(record["gold"]),
            record["oracle_forecast"],
            record["initial_snapshot"],
            record["final_snapshot"],
            record["score"]["confirmation_observed"],
        )
    task = record["final_task"]
    run = task.get("agent_run") or {}
    unchanged = record["initial_snapshot"] == record["final_snapshot"] and not task.get("actions")
    response = (
        task["status"] == "waiting_input" and bool(run.get("question")) and run.get("options") == []
    )
    if case["kind"] == "missing_reading_first_response":
        response = response or (
            task["status"] == "failed"
            and run.get("failure_code") == "forecast_unavailable"
            and task.get("message") == case["expected_oracle_error"]
        )
    if case["kind"] == "infeasible_first_response":
        response = (
            response
            and d4.same_goal(run.get("goal"), record["gold"])
            and bool(record["oracle_forecast"])
            and not d4.optimal_ids(record["oracle_forecast"], case["priority"])
        )
    binding = review_binding(record)
    accepted = bool(
        review
        and review.get("correct") is True
        and review.get("reviewer")
        and review.get("reason")
        and all(review.get(k) == v for k, v in binding.items())
    )
    passed = bool(unchanged and response and accepted)
    return dict(
        case_pass=passed,
        understanding_correct=passed,
        goal_completed=None,
        preference_correct=None,
        exception_correct=passed,
        all_actions_verified=None,
        confirmation_observed=record["score"]["confirmation_observed"],
        unexpected_write=not unchanged,
        false_success=task["status"] == "succeeded",
        review_status="accepted"
        if passed
        else "pending"
        if unchanged and response
        else "automatic_failure",
        semantic_review_required=True,
        structural_exception_correct=bool(unchanged and response),
    )


def run_trial(case, strategy, pair, model, *, repetition, source="controlled_test", capture=None):
    record = d4.run_trial(
        case,
        strategy,
        pair,
        model,
        source=source,
        phase=f"d5-r{repetition}",
        capture=capture,
        approve_plan=approve_plan,
    )
    record.update(
        split="acceptance_new_at_freeze_same_author",
        repetition=repetition,
        run_id=run_id(case["id"], repetition, strategy),
    )
    record["score_before_d5_audit"] = record["score"]
    record["score"] = score_record(record)
    if case["kind"] != "execute":
        record["review_binding"] = review_binding(record)
    return record


def failed_record(case, strategy, repetition, error_type, capture):
    record = d4.failed_record(case, strategy, error_type, capture)
    record.update(
        split="acceptance_new_at_freeze_same_author",
        repetition=repetition,
        run_id=run_id(case["id"], repetition, strategy),
    )
    record["score"]["understanding_correct"] = False
    return record


def summarize(records, ledger):
    result = dict(
        limit=LIMIT,
        shared_used=ledger.used,
        not_run=[
            run_id(*item)
            for item in schedule()
            if run_id(*item) not in {r["run_id"] for r in records}
        ],
        script_errors=[r["run_id"] for r in records if r.get("error")],
        pending_semantic_review=[
            r["run_id"] for r in records if r["score"].get("review_status") == "pending"
        ],
    )
    for label, first in (("first_pass", True), ("preselected_repeats", False)):
        selected = [r for r in records if (r["repetition"] == 1) == first]
        result[label] = {}
        for strategy in d4.STRATEGIES:
            subset = [r for r in selected if r["strategy"] == strategy]
            result[label][strategy] = {
                key: dict(
                    numerator=sum(
                        bool(r["score"].get(key)) for r in subset if r["score"].get(key) is not None
                    ),
                    denominator=sum(r["score"].get(key) is not None for r in subset),
                )
                for key in METRICS
            }
        result[label]["paired"] = []
        for case_id, rep in dict.fromkeys((r["case_id"], r["repetition"]) for r in selected):
            pair = [
                next(
                    (
                        r
                        for r in selected
                        if r["case_id"] == case_id and r["repetition"] == rep and r["strategy"] == s
                    ),
                    None,
                )
                for s in d4.STRATEGIES
            ]
            if all(pair):
                complete = all(r["score"].get("goal_completed") is True for r in pair)
                result[label]["paired"].append(
                    dict(
                        case_id=case_id,
                        repetition=rep,
                        pass_S1=pair[0]["score"]["case_pass"],
                        pass_M=pair[1]["score"]["case_pass"],
                        energy_wh_S1=pair[0]["scope_energy_wh"] if complete else None,
                        energy_wh_M=pair[1]["scope_energy_wh"] if complete else None,
                    )
                )
    return result


def run_real(args):
    sys.path.insert(0, str(ROOT / "backend/src"))
    from homemind.agent.model import DeepSeekModel

    batch = validate_batch(args.batch)
    manifest = validate_freeze(batch)
    config = d4.base.configuration()
    if (
        not config.model_enabled
        or not config.model_api_key
        or config.model_name != MODEL["name"]
        or config.model_provider != MODEL["provider"]
        or config.model_base_url != MODEL["base_url"]
    ):
        raise ValueError("frozen_model_configuration_required")
    lock_path = batch / "batch.lock"
    lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        fingerprint = d4.digest(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode())
        ledger = open_budget(batch / "budget.json", fingerprint, resume=args.resume)
        directory = batch / "records"
        directory.mkdir(exist_ok=True)
        records = [
            json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("A*.json"))
        ]
        planned = {run_id(*item) for item in schedule()}
        if len({r["run_id"] for r in records}) != len(records) or any(
            r["run_id"] not in planned for r in records
        ):
            raise ValueError("saved_records_do_not_match_schedule")
        model = d4.base.BudgetedModel(DeepSeekModel(config), ledger)
        cases = {c["id"]: c for c in load_cases()}
        for case_id, rep, strategy in schedule():
            identifier = run_id(case_id, rep, strategy)
            if any(r["run_id"] == identifier for r in records):
                continue
            if any(r["case_id"] == identifier for r in ledger.data["requests"]):
                raise ValueError("orphan_issued_request_no_automatic_replay")
            if not can_start_trial(ledger):
                break
            model.case_id = identifier
            before, capture = ledger.used, {}
            case = cases[case_id]
            try:
                pair = prepare_pair(case, batch / ".fixtures" / case_id)
                record = run_trial(
                    case,
                    strategy,
                    pair,
                    model,
                    repetition=rep,
                    source="real_model",
                    capture=capture,
                )
            except Exception as error:
                record = failed_record(case, strategy, rep, type(error).__name__, capture)
            record.update(issued_requests=ledger.used - before, shared_requests_after=ledger.used)
            d4.base.write_new(directory / (identifier.replace("/", "-") + ".json"), record)
            records.append(record)
            d4.base.save(batch / "summary.json", summarize(records, ledger))
            print(
                json.dumps(
                    dict(run_id=identifier, score=record["score"], shared_requests=ledger.used)
                ),
                flush=True,
            )
            if record.get("error"):
                return 1
        d4.base.save(batch / "summary.json", summarize(records, ledger))
        return 0
    finally:
        os.close(lock)
        lock_path.unlink(missing_ok=True)


def audit_reviews(batch, reviews_path):
    """Append scored copies; preserve originals and the shared request ledger."""
    reviews = json.loads(Path(reviews_path).read_text(encoding="utf-8"))
    target = Path(batch) / "reviewed"
    target.mkdir(exist_ok=False)
    records = []
    for path in sorted((Path(batch) / "records").glob("A*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        record["original_record_sha256"] = d4.digest(path.read_bytes())
        review = reviews.get(record["run_id"])
        if review:
            record["semantic_review"] = review
            record["semantic_review_sha256"] = d4.digest(
                json.dumps(review, sort_keys=True, ensure_ascii=False).encode()
            )
        if not record.get("error"):
            record["original_score"] = record["score"]
            record["score"] = score_record(record, review)
        d4.base.write_new(target / path.name, record)
        records.append(record)
    used = json.loads((Path(batch) / "budget.json").read_text(encoding="utf-8"))["used"]
    d4.base.write_new(target / "summary.json", summarize(records, SimpleNamespace(used=used)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--real", action="store_true")
    mode.add_argument("--audit-reviews", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--batch", type=Path, default=BATCH)
    args = parser.parse_args()
    if not (args.real or args.freeze or args.audit_reviews):
        print(
            json.dumps(
                dict(status="not_run", cases=12, planned_runs=36, limit=LIMIT, real_requests=0)
            )
        )
        return 0
    try:
        batch = validate_batch(args.batch)
        if args.freeze:
            freeze(batch)
            print(json.dumps(dict(status="frozen", cases=12, planned_runs=36, real_requests=0)))
            return 0
        if args.audit_reviews:
            audit_reviews(batch, args.audit_reviews)
            return 0
        with d4.base.official_http_only():
            return run_real(args)
    except Exception:
        print(
            json.dumps(dict(status="not_completed", reason="inspect_saved_batch_or_configuration"))
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
