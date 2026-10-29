"""Opt-in D4 development pairs. Default lists cases; no configuration or network."""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import product_eval as base

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evaluation/product-d4-cases.json"
BATCH = ROOT / "output/product-d4-real-20261029"
STRATEGIES = ("single_forecast", "expert_forecast")
LIMIT = 40


def load_cases():
    return json.loads(CASES.read_text(encoding="utf-8"))


def validate_batch(path):
    if Path(path).resolve() != BATCH.resolve():
        raise ValueError("one_fixed_shared_authorization_batch_only")
    return BATCH


def open_budget(path, fingerprint, *, resume):
    return base.BudgetLedger(path, limit=LIMIT, fingerprint=fingerprint, resume=resume)


def can_start_trial(ledger):
    # Single-round D4 has no scripted answers. Its program cap is six calls.
    # Do not enter a graph which could exhaust the batch mid-call and inflate
    # application counts with a wrapper attempt that never reached the provider.
    return LIMIT - ledger.used >= 6


def optimal_ids(forecast, priority):
    feasible = [c for c in forecast["candidates"] if c["deadline_met"]]
    if not feasible:
        return []

    def rank(c):
        values = (c["first_observed_goal_minute"], c["energy_wh"])
        return values if priority == "comfort_first" else values[::-1]

    best = min(map(rank, feasible))
    return [c["id"] for c in feasible if rank(c) == best]


def preference_correct(selected, forecast, priority):
    return selected is not None and selected in optimal_ids(forecast, priority)


def backup(source, target):
    if target.exists():
        raise FileExistsError("trial_database_must_not_be_reused")
    with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
        source_db.backup(target_db)


def prepare_pair(case, directory):
    """Gold is constructed from predeclared requirements, never from model output."""
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
            or digest(Path(pair["template"]).read_bytes()) != pair["template_sha256"]
        ):
            raise ValueError("frozen_fixture_changed")
        return pair
    template = directory / "initial.sqlite"
    if template.exists():
        raise ValueError("partial_fixture_requires_inspection_not_reset")
    with base.synthetic_client(template) as client:
        initial = base.checked(client.get("/simulation"))
        rooms = {r["name"]: r["id"] for r in initial["rooms"]}
        living = {e["type"]: e["id"] for e in initial["entities"] if e["room_id"] == rooms["客厅"]}
        keeps = []
        if "reading_light" in case["setup"]:
            snapshot = base.checked(
                client.post(
                    "/simulation/entities",
                    json={"room_id": rooms["卧室"], "name": "卧室阅读灯", "type": "light"},
                )
            )
            lamp = next(e for e in snapshot["entities"] if e["name"] == "卧室阅读灯")
            base.checked(
                client.post(
                    "/simulation/controls/" + lamp["id"],
                    json={"action": "set_light", "parameters": {"brightness_pct": 45}},
                )
            )
            keeps.append(lamp["id"])
        if "half_cover" in case["setup"]:
            base.checked(
                client.post(
                    "/simulation/controls/" + living["cover"],
                    json={"action": "set_cover", "parameters": {"position_pct": 50}},
                )
            )
            keeps.append(living["cover"])
        if "window_unknown" in case["setup"]:
            base.checked(
                client.post(
                    "/simulation/events", json={"entity_id": living["window"], "known": False}
                )
            )
        initial = base.checked(client.get("/simulation"))
        username = base.checked(client.get("/auth/session"))["user"]["username"]
        gold = dict(
            kind="goal",
            room_id=rooms["客厅"],
            climate_entity_id=living["climate"],
            cover_entity_id=living["cover"],
            target_temperature_c=26,
            ready_in_minutes=case["minutes"],
            priority=case["priority"],
            allowed_fan_modes=case["fans"],
            cover_constraint=case["cover"],
            keep_entity_ids=keeps,
            protected_room_ids=[rooms["卧室"]],
        )

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
                try:
                    return forecast_plan(engine, gold), None, baseline
                except SimulationError as error:
                    return None, error.code, baseline

        forecast, failure, baseline = client.portal.call(oracle)
    pair = dict(
        case=case,
        template=str(template),
        template_sha256=digest(template.read_bytes()),
        username=username,
        gold=gold,
        forecast=forecast,
        oracle_failure=failure,
        scope_initial_watt_minutes=baseline,
        initial_snapshot=initial,
        directory=str(directory),
    )
    base.write_new(descriptor, pair)
    return pair


@contextmanager
def trial_client(path, username):
    from fastapi.testclient import TestClient
    from homemind.app import create_app
    from homemind.config import Settings
    from homemind.persistence.database import Database

    database = Database(f"sqlite+aiosqlite:///{path}", instance_id="product-c-synthetic")
    app = create_app(
        Settings(
            _env_file=None,
            environment="test",
            database_url=None,
            model_enabled=False,
            simulation_debug_enabled=True,
            allowed_origins=["http://testserver"],
        ),
        database=database,
    )
    with TestClient(app) as client:
        session = base.checked(client.get("/auth/session"))
        client.headers.update(
            {"Origin": "http://testserver", "X-CSRF-Token": session["csrf_token"]}
        )
        user = base.checked(
            client.post(
                "/auth/login", json={"username": username, "password": "synthetic test password"}
            )
        )
        client.headers["X-CSRF-Token"] = user["csrf_token"]
        yield client


def same_goal(actual, gold):
    if not actual or set(actual) != set(gold):
        return False
    extra_keeps = set(actual.get("keep_entity_ids", [])) - set(gold.get("keep_entity_ids", []))
    if extra_keeps & {gold.get("climate_entity_id"), gold.get("cover_entity_id")}:
        return False
    return all(
        (
            set(v).issubset(actual[k])
            if k == "keep_entity_ids"
            else set(actual[k]) == set(v)
            if isinstance(v, list)
            else actual[k] == v
        )
        for k, v in gold.items()
    )


def hard_plan_matches(task, gold, forecast):
    run = task.get("agent_run") or {}
    selected = next(
        (
            c
            for c in (forecast or {}).get("candidates", [])
            if c["id"] == run.get("selected_candidate_id")
        ),
        None,
    )
    plan = run.get("proposed_plan") or {}
    return bool(
        selected
        and selected["deadline_met"]
        and same_goal(run.get("goal"), gold)
        and sorted(plan.get("actions", []), key=lambda a: a["entity_id"])
        == sorted(selected["actions"], key=lambda a: a["entity_id"])
        and plan.get("ready_in_minutes") == gold["ready_in_minutes"]
        and plan.get("temperatures") == [dict(room_id=gold["room_id"], target=26)]
        and set(plan.get("keep_entity_ids", [])) == set(run["goal"]["keep_entity_ids"])
        and set(plan.get("protected_room_ids", [])) == set(gold["protected_room_ids"])
    )


def score(case, task, gold, forecast, initial, final, confirmation):
    run = task.get("agent_run") or {}
    candidate = next(
        (
            c
            for c in (forecast or {}).get("candidates", [])
            if c["id"] == run.get("selected_candidate_id")
        ),
        None,
    )
    allowed = {a["entity_id"] for a in candidate["actions"]} if candidate else set()
    before = {e["id"]: e for e in initial["entities"]}
    outside = [
        e["id"]
        for e in final["entities"]
        if e["type"] in {"climate", "cover", "light"}
        and e["id"] not in allowed
        and e["state"] != before[e["id"]]["state"]
    ]
    actions = task.get("actions", [])
    unexpected = bool(outside or any(a["entity_id"] not in allowed for a in actions))
    execute = case["kind"] == "execute"
    result = dict(
        case_pass=False,
        understanding_correct=None,
        goal_completed=None,
        preference_correct=None,
        exception_correct=None,
        all_actions_verified=None,
        confirmation_observed=confirmation,
        unexpected_write=unexpected,
        false_success=False,
    )
    if execute:
        result["understanding_correct"] = same_goal(run.get("goal"), gold)
        result["preference_correct"] = bool(
            result["understanding_correct"]
            and forecast
            and preference_correct(run.get("selected_candidate_id"), forecast, gold["priority"])
        )
        expected_ids = [a["entity_id"] for a in candidate["actions"]] if candidate else []
        verified = bool(
            expected_ids
            and len(actions) == len(expected_ids)
            and {a["entity_id"] for a in actions} == set(expected_ids)
            and all(a["status"] == "verified" for a in actions)
        )
        result["all_actions_verified"] = verified and not unexpected
        due = initial["simulated_minutes"] + gold["ready_in_minutes"]
        evidence = task.get("plan", {}).get("deadline_evidence", {}).get(gold["room_id"], {})
        room = next(r for r in final["rooms"] if r["id"] == gold["room_id"])
        completed = bool(
            hard_plan_matches(task, gold, forecast)
            and verified
            and confirmation
            and task["status"] == "succeeded"
            and not unexpected
            and final["simulated_minutes"] == due
            and evidence.get("checked_at_minutes") == due
            and evidence.get("outcome") == "verified"
            and room["temperature_c"] is not None
            and room["temperature_c"] <= 26
        )
        result["goal_completed"] = completed
        result["case_pass"] = completed and result["preference_correct"]
        result["false_success"] = task["status"] == "succeeded" and not completed
    else:
        unchanged = final == initial and not actions
        if case["kind"] == "infeasible_first_response":
            correct = bool(
                unchanged
                and task["status"] == "waiting_input"
                and run.get("question")
                and run.get("options") == []
                and same_goal(run.get("goal"), gold)
                and forecast
                and not optimal_ids(forecast, gold["priority"])
            )
        else:
            correct = bool(
                unchanged
                and task["status"] == "failed"
                and run.get("failure_code") == "forecast_unavailable"
                and task.get("message") == "所有参与物理过程的窗户和占用感知须存在且可观测"
            )
        result["exception_correct"] = result["case_pass"] = correct
        result["false_success"] = task["status"] == "succeeded"
    return result


def run_trial(
    case,
    strategy,
    pair,
    model,
    *,
    source="controlled_test",
    phase="phase1",
    capture=None,
    approve_plan=None,
):
    path = Path(pair["directory"]) / (phase + "-" + strategy + ".sqlite")
    backup(pair["template"], path)
    with trial_client(path, pair["username"]) as client:
        initial = base.checked(client.get("/simulation"))
        if initial != pair["initial_snapshot"]:
            raise ValueError("paired_initial_snapshot_mismatch")
        client.app.state.agent_model = model
        started = time.monotonic()
        task = base.checked(
            client.post(
                "/tasks/agent",
                json={
                    "text": case["text"],
                    "expected_world_id": initial["world_id"],
                    "strategy": strategy,
                },
                headers={"Idempotency-Key": "d4-" + uuid4().hex},
            )
        )
        planning_ms = round((time.monotonic() - started) * 1000)
        first = json.loads(json.dumps(task))
        if capture is not None:
            capture.update(
                initial_snapshot=initial,
                first_task=first,
                final_task=task,
                planning_api_ms=planning_ms,
            )
        confirmation = task["status"] == "waiting_confirmation"
        # The same scripted reviewer approves every hard-valid original choice,
        # including preference-suboptimal choices. Never substitute the oracle choice.
        if confirmation and (approve_plan or hard_plan_matches)(
            task, pair["gold"], pair["forecast"]
        ):
            task = base.checked(
                client.post(
                    f"/tasks/{task['id']}/confirm",
                    json={"expected_turn": task["agent_run"]["turn"]},
                    headers={"Idempotency-Key": "d4-confirm-" + uuid4().hex},
                )
            )
            if capture is not None:
                capture["final_task"] = task
            if task["status"] in {"partial", "waiting_verification"}:
                now = base.checked(client.get("/simulation"))
                task = base.checked(
                    client.post(
                        f"/tasks/{task['id']}/advance",
                        json={
                            "expected_world_id": now["world_id"],
                            "expected_simulated_minutes": now["simulated_minutes"],
                        },
                        headers={"Idempotency-Key": "d4-advance-" + uuid4().hex},
                    )
                )
        final = base.checked(client.get("/simulation"))
        if capture is not None:
            capture.update(final_task=task, final_snapshot=final)

        async def actual_energy():
            from homemind.simulation.physics import energy_wh

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

        scope_energy = client.portal.call(actual_energy)
        return dict(
            case_id=case["id"],
            strategy=strategy,
            phase=phase,
            source=source,
            split="development",
            database="isolated_sqlite",
            devices="simulation",
            text=case["text"],
            gold=pair["gold"],
            oracle_forecast=pair["forecast"],
            oracle_failure=pair["oracle_failure"],
            initial_snapshot=initial,
            first_task=first,
            final_task=task,
            final_snapshot=final,
            scope_energy_wh=scope_energy,
            planning_api_ms=planning_ms,
            elapsed_ms=round((time.monotonic() - started) * 1000),
            score=score(case, task, pair["gold"], pair["forecast"], initial, final, confirmation),
        )


def digest(data):
    return hashlib.sha256(data).hexdigest()


def source_hashes():
    paths = [
        CASES,
        Path(__file__),
        Path(base.__file__),
        *sorted((ROOT / "backend/src/homemind").rglob("*.py")),
    ]
    return {
        p.relative_to(ROOT).as_posix(): digest(p.read_bytes().replace(b"\r\n", b"\n"))
        for p in paths
    }


def failed_record(case, strategy, error_type, capture):
    execute = case["kind"] == "execute"
    metrics = {
        key: False if execute else None
        for key in (
            "understanding_correct",
            "goal_completed",
            "preference_correct",
            "all_actions_verified",
        )
    }
    metrics.update(
        case_pass=False,
        exception_correct=None if execute else False,
        false_success=None,  # A scorer failure cannot prove a product false-success event.
        unexpected_write=None,
    )
    return dict(
        case_id=case["id"],
        strategy=strategy,
        source="real_model",
        split="development",
        error="evaluation_script_error",
        error_type=error_type,
        score=metrics,
        **capture,
    )


def summarize(records, planned, ledger):
    metrics = {}
    for strategy in STRATEGIES:
        subset = [r for r in records if r["strategy"] == strategy]
        metrics[strategy] = {}
        for key in (
            "case_pass",
            "understanding_correct",
            "goal_completed",
            "preference_correct",
            "exception_correct",
            "all_actions_verified",
        ):
            values = [r["score"][key] for r in subset if r["score"].get(key) is not None]
            metrics[strategy][key] = dict(
                numerator=sum(bool(v) for v in values), denominator=len(values)
            )
    return dict(
        metrics=metrics,
        shared_used=ledger.used,
        limit=LIMIT,
        not_run=[key for key in planned if key not in {r["run_id"] for r in records}],
        script_errors=[r["run_id"] for r in records if r.get("error")],
    )


def run_real(args):
    sys.path.insert(0, str(ROOT / "backend/src"))
    from homemind.agent.model import DeepSeekModel

    batch = validate_batch(args.batch)
    config = base.configuration()
    if not config.model_enabled or not config.model_api_key:
        raise ValueError("model_not_configured")
    batch.mkdir(parents=True, exist_ok=True)
    lock_path = batch / "batch.lock"
    lock = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        cases, hashes = load_cases(), source_hashes()
        fingerprint = digest(CASES.read_bytes())
        phase = "phase2" if args.retest else "phase1"
        ledger = open_budget(
            batch / "budget.json", fingerprint, resume=args.resume or bool(args.retest)
        )
        if args.retest:
            first_manifest = json.loads(
                (batch / "phase1/manifest.json").read_text(encoding="utf-8")
            )
            first_records = [
                json.loads(p.read_text(encoding="utf-8"))
                for p in (batch / "phase1").glob("DD*.json")
            ]
            failures = {
                r["case_id"]
                for r in first_records
                if not r["score"]["case_pass"] and not r.get("error")
            }
            if (
                not set(args.retest) <= failures
                or hashes == first_manifest["hashes"]
                or config.model_name != first_manifest["model"]
            ):
                raise ValueError("retest_needs_actual_failure_source_change_same_model")
            cases = [c for c in cases if c["id"] in args.retest]
        order = [
            (c, s)
            for i, c in enumerate(cases)
            for s in (STRATEGIES if i % 2 == 0 else STRATEGIES[::-1])
        ]
        planned = [c["id"] + "/" + s for c, s in order]
        directory = batch / phase
        directory.mkdir(exist_ok=True)
        manifest = dict(
            date="2026-10-29 Asia/Shanghai",
            hashes=hashes,
            model=config.model_name,
            thinking="disabled",
            max_tokens=2048,
            temperature="provider_default",
            order=planned,
            prior_calls=ledger.used,
            limit=LIMIT,
            split="development",
            git_head=subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            comparison="E_end_to_end_only",
            human_wait="scripted_immediate_confirm_no_answers",
            scope_note="DD04/DD06 first response only; no recovery journey or P layer",
        )
        manifest_path = directory / "manifest.json"
        if args.resume:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            if (
                previous["hashes"] != hashes
                or previous["model"] != config.model_name
                or previous["order"] != planned
            ):
                raise ValueError("resume_sources_model_or_order_changed")
        else:
            base.write_new(manifest_path, manifest)
        records = [json.loads(p.read_text(encoding="utf-8")) for p in directory.glob("DD*.json")]
        model = base.BudgetedModel(DeepSeekModel(config), ledger)
        for case, strategy in order:
            run_id = case["id"] + "/" + strategy
            if any(r["run_id"] == run_id for r in records):
                continue
            if not can_start_trial(ledger):
                break
            model.case_id = phase + "/" + run_id
            prior = ledger.used
            if any(r["case_id"] == model.case_id for r in ledger.data["requests"]):
                raise ValueError("interrupted_request_requires_inspection_not_replay")
            capture = {}
            try:
                pair = prepare_pair(case, batch / ".fixtures" / case["id"])
                record = run_trial(
                    case, strategy, pair, model, source="real_model", phase=phase, capture=capture
                )
            except Exception as error:
                record = failed_record(case, strategy, type(error).__name__, capture)
            record.update(
                run_id=run_id,
                issued_requests=ledger.used - prior,
                shared_requests_after=ledger.used,
            )
            base.write_new(directory / (case["id"] + "-" + strategy + ".json"), record)
            records.append(record)
            base.save(directory / "summary.json", summarize(records, planned, ledger))
            print(
                json.dumps(dict(run_id=run_id, score=record["score"], shared_requests=ledger.used)),
                flush=True,
            )
            if record.get("error"):
                return 1
        base.save(directory / "summary.json", summarize(records, planned, ledger))
        return 0
    finally:
        os.close(lock)
        lock_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retest", nargs="+", choices=[c["id"] for c in load_cases()])
    parser.add_argument("--batch", type=Path, default=BATCH)
    args = parser.parse_args()
    if not args.real:
        print(
            json.dumps(
                dict(status="not_run", cases=len(load_cases()), strategies=2, real_requests=0)
            )
        )
        return 0
    try:
        with base.official_http_only():
            return run_real(args)
    except Exception:
        print(
            json.dumps(dict(status="not_completed", reason="inspect_saved_batch_or_configuration"))
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
