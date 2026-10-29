"""Short household transactions around bounded, transaction-free model rounds."""

import asyncio
import time
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select

from homemind.agent.forecast import clone_engine, validate_selection
from homemind.agent.graph import PlannerCancelled, run_planner
from homemind.agent.pipeline import run_pipeline
from homemind.agent.validation import ambiguous_question, validate_options, validate_plan
from homemind.executor import execute, verify
from homemind.persistence.codec import save_engine
from homemind.persistence.models import Preference, Task
from homemind.preferences import preference_view
from homemind.simulation.models import SimulationError
from homemind.tasks import detail, request_hash, task_by_id

EMPTY_PLAN = {"actions": [], "constraints": [], "temperatures": [], "due_at_minutes": None}

FAILURE_MESSAGES = {
    "model_timeout": "模型单次请求超时，本轮未发送设备动作，请稍后重新提交",
    "round_timeout": "本轮规划超过65秒预算，未发送设备动作，请简化需求后重新提交",
    "model_unavailable": "模型服务暂不可用，请检查本项目模型配置或稍后重试",
    "invalid_output": "模型输出未通过严格格式校验，未发送设备动作，请重新提交",
    "invalid_tool": "模型请求了未授权工具或参数，未发送设备动作",
    "model_budget": "本轮已达模型调用上限，未发送设备动作，请简化需求",
    "task_model_budget": "任务已达12次模型调用上限，未发送设备动作，请重新提交明确需求",
    "tool_budget": "本轮已达6次只读工具调用上限，未发送设备动作，请简化需求",
    "analysis_incomplete": "专家分析未完成，本轮未发送设备动作；请查看角色记录或重新提交",
}

EXPERIMENTAL_STRATEGIES = {"single_forecast", "expert_forecast"}


def agent_mode(strategy):
    return "multi_agent" if strategy == "expert_forecast" else "single_agent"


def public_config(app):
    available = app.state.agent_model is not None
    return {
        "available": available,
        "model": app.state.settings.model_name,
        "reason": None if available else "自然语言任务尚未配置模型，请使用规则模板",
        "strategies": ["standard", "single_forecast", "expert_forecast"]
        if app.state.settings.simulation_debug_enabled
        else ["standard"],
    }


def claim(database, home_id):
    if home_id in database.busy:
        raise SimulationError(409, "home_busy", "当前家庭正在处理任务，请稍后重试")
    database.busy.add(home_id)


def check_turn(task, expected_turn, status):
    if (
        task.mode not in {"single_agent", "multi_agent"}
        or task.mode != agent_mode((task.agent_run or {}).get("strategy", "standard"))
        or task.mode != agent_mode((task.request or {}).get("strategy", "standard"))
        or task.agent_run["turn"] != expected_turn
        or task.status != status
    ):
        raise SimulationError(409, "turn_conflict", "任务轮次或状态已变化，请重新读取当前任务")


def check_replay(task, key, digest, kind):
    operation = (task.agent_run or {}).get("operations", {}).get(key)
    if operation:
        if operation["hash"] != digest or operation["kind"] != kind:
            raise SimulationError(409, "idempotency_conflict", "此幂等键已用于不同操作")
        return True
    if key == task.idempotency_key:
        raise SimulationError(409, "idempotency_conflict", "请为每轮操作使用独立幂等键")
    return False


def operation(run, key, digest, kind):
    run["operations"][key] = {"hash": digest, "kind": kind, "turn": run["turn"]}


def check_creation_replay(task, digest):
    if (
        task.mode not in {"single_agent", "multi_agent"}
        or task.mode != agent_mode((task.request or {}).get("strategy", "standard"))
        or task.mode != agent_mode((task.agent_run or {}).get("strategy", "standard"))
        or task.request_hash != digest
    ):
        raise SimulationError(409, "idempotency_conflict", "此幂等键已用于不同请求或模式")


def mark_failure(
    task,
    code,
    message="本次方案未执行，请查看原因并重新提交",
    *,
    diagnostic=None,
    public_record=None,
):
    task.status = "failed"
    task.message = message[:255]
    run = deepcopy(task.agent_run)
    run["failure_code"] = code
    if diagnostic is not None:
        run["diagnostic"] = diagnostic
    if public_record is not None:
        run["records"].append(public_record)
    run["records"].append({"stage": "failed", "message": message})
    task.agent_run = run
    task.updated_at = int(time.time())


def same_facts(task, engine):
    current = engine.snapshot()
    return all(
        current[key] == task.initial_snapshot[key]
        for key in ("world_id", "revision", "config_revision")
    )


def add_timing(task, stage, started):
    duration = round((time.monotonic() - started) * 1000)
    run = deepcopy(task.agent_run)
    run["timings"][stage + "_ms"] += duration
    run["records"].append(
        {
            "stage": stage,
            "message": {
                "validation": "方案程序校验已结束",
                "execution": "设备执行及独立核验已结束",
            }[stage],
            "duration_ms": duration,
        }
    )
    task.agent_run = run


def record_round(task, result):
    updated = deepcopy(task.agent_run)
    previous_calls = updated["model_calls"]
    updated["model_calls"] += result["model_calls"]
    updated["tool_calls"] += result["tool_calls"]
    if result["model_calls"]:
        updated["usage"] = (
            {
                key: (updated["usage"] or {}).get(key, 0) + result["usage"][key]
                for key in ("input_tokens", "output_tokens")
            }
            if result["usage"] is not None and (not previous_calls or updated["usage"] is not None)
            else None
        )
        updated["actual_model"] = result["actual_model"]
    updated["records"].extend(result["records"])
    updated["timings"]["planning_ms"] += result["elapsed_ms"]
    updated["rounds"].append(
        {key: result[key] for key in ("model_calls", "tool_calls", "usage", "elapsed_ms")}
        | {"turn": updated["turn"]}
    )
    if updated.get("strategy") == "expert_forecast":
        updated["role_runs"] = result.get("role_runs", [])
        updated["rounds"][-1]["roles"] = [
            {key: value for key, value in role.items() if key != "advice"}
            for role in updated["role_runs"]
        ]
    if updated.get("strategy") in EXPERIMENTAL_STRATEGIES:
        for key in ("goal", "forecast", "selected_candidate_id", "preference_optimal"):
            updated[key] = result.get(key)
    task.agent_run = updated
    return updated


async def create_agent(request, body, key):
    app, home_id = request.app, request.state.home_id
    database = app.state.database
    normalized = body.model_dump()
    experimental = normalized["strategy"] in EXPERIMENTAL_STRATEGIES
    if not experimental:
        normalized.pop("strategy")
    digest = request_hash(normalized)
    async with database.sessions() as session:
        previous = await session.scalar(
            select(Task).where(Task.home_id == home_id, Task.idempotency_key == key)
        )
        if previous:
            check_creation_replay(previous, digest)
            return await detail(session, previous)
    if app.state.agent_model is None:
        raise SimulationError(503, "model_unavailable", "自然语言任务尚未配置模型，请使用规则模板")
    if experimental and not app.state.settings.simulation_debug_enabled:
        raise SimulationError(422, "simulation_debug_required", "方案权衡需要开启仿真调试模式")
    claim(database, home_id)
    task_id = uuid4().hex
    try:
        async with database.home(home_id, save=False) as (session, _, engine):
            # Initial read and occupancy claim are separated by await boundaries.
            # A same-key request may have finished before this request acquired the home.
            previous = await session.scalar(
                select(Task).where(Task.home_id == home_id, Task.idempotency_key == key)
            )
            if previous:
                check_creation_replay(previous, digest)
                return await detail(session, previous)
            if body.expected_world_id != engine._world_id:
                raise SimulationError(409, "world_changed", "仿真环境已重置，请刷新后重新提交")
            for entity_id in body.keep_entity_ids:
                engine._entity(entity_id)
            for room_id in body.protected_room_ids:
                engine._room(room_id)
            now = int(time.time())
            preferences = preference_view(await session.get(Preference, home_id))
            snapshot = engine.snapshot()
            exact = None
            if experimental:
                try:
                    exact = clone_engine(engine)
                except SimulationError:
                    pass
            task = Task(
                id=task_id,
                home_id=home_id,
                idempotency_key=key,
                request_hash=digest,
                request=normalized,
                mode=agent_mode(body.strategy),
                scenario="local",
                status="planning",
                world_id=engine._world_id,
                initial_snapshot=snapshot,
                final_snapshot=snapshot,
                preferences_snapshot=preferences,
                plan=deepcopy(EMPTY_PLAN),
                verification={},
                message="正在理解需求并规划",
                created_at=now,
                updated_at=now,
                agent_run={
                    "turn": 0,
                    "max_replies": 3,
                    "question": None,
                    "options": [],
                    "proposed_plan": None,
                    "rationale": None,
                    "model_calls": 0,
                    "tool_calls": 0,
                    "usage": None,
                    "records": [],
                    "rounds": [],
                    "timings": {"planning_ms": 0, "validation_ms": 0, "execution_ms": 0},
                    "failure_code": None,
                    "operations": {},
                    "conversation": [
                        {
                            "role": "user",
                            "text": body.text,
                            "keep_entity_ids": body.keep_entity_ids,
                            "protected_room_ids": body.protected_room_ids,
                        }
                    ],
                },
            )
            session.add(task)
            if experimental:
                task.agent_run = task.agent_run | dict(
                    strategy=body.strategy,
                    pipeline_version="d3-experts-v1"
                    if body.strategy == "expert_forecast"
                    else "d2-forecast-v1",
                    goal=None,
                    forecast=None,
                    selected_candidate_id=None,
                    preference_optimal=None,
                )
                if body.strategy == "expert_forecast":
                    task.agent_run = task.agent_run | {"role_runs": []}
        return await plan_round(app, home_id, task_id, exact)
    finally:
        database.busy.discard(home_id)


async def reply_agent(request, task_id, body, key):
    app, home_id = request.app, request.state.home_id
    database = app.state.database
    digest = request_hash(body.model_dump())
    async with database.sessions() as session:
        task = await task_by_id(session, home_id, task_id)
        if check_replay(task, key, digest, "reply"):
            return await detail(session, task)
        check_turn(task, body.expected_turn, "waiting_input")
        if task.agent_run["turn"] >= 3:
            raise SimulationError(409, "reply_budget", "补充回答已达三次上限，请重新提交")
        if (
            sum(len(item["text"]) for item in task.agent_run["conversation"]) + len(body.text)
            > 8000
        ):
            raise SimulationError(422, "input_budget", "完整需求及回答超过8000字符")
    if app.state.agent_model is None:
        raise SimulationError(503, "model_unavailable", "自然语言模型暂不可用")
    claim(database, home_id)
    try:
        async with database.home(home_id, save=False) as (session, _, engine):
            task = await task_by_id(session, home_id, task_id)
            if check_replay(task, key, digest, "reply"):
                return await detail(session, task)
            check_turn(task, body.expected_turn, "waiting_input")
            if task.world_id != engine._world_id:
                raise SimulationError(409, "world_changed", "仿真环境已重置，请重新提交")
            run = deepcopy(task.agent_run)
            run["turn"] += 1
            run["question"], run["options"] = None, []
            exact = None
            if run.get("strategy") in EXPERIMENTAL_STRATEGIES:
                for field in (
                    "goal",
                    "forecast",
                    "selected_candidate_id",
                    "preference_optimal",
                    "proposed_plan",
                    "rationale",
                    "failure_code",
                ):
                    run[field] = None
                run.pop("diagnostic", None)
                if run.get("strategy") == "expert_forecast":
                    run["role_runs"] = []
                try:
                    exact = clone_engine(engine)
                except SimulationError:
                    pass
            run["conversation"].append({"role": "user", "text": body.text})
            operation(run, key, digest, "reply")
            task.agent_run = run
            task.status, task.message = "planning", "正在根据补充信息规划"
            task.initial_snapshot = engine.snapshot()
            task.preferences_snapshot = preference_view(await session.get(Preference, home_id))
            task.updated_at = int(time.time())
        return await plan_round(app, home_id, task_id, exact)
    finally:
        database.busy.discard(home_id)


async def plan_round(app, home_id, task_id, exact=None):
    database = app.state.database
    async with database.sessions() as session:
        task = await task_by_id(session, home_id, task_id)
        snapshot, preferences, run = (
            task.initial_snapshot,
            task.preferences_snapshot,
            task.agent_run,
        )
    try:
        if run.get("strategy") in EXPERIMENTAL_STRATEGIES:
            result = await run_pipeline(
                app.state.agent_model,
                snapshot,
                preferences,
                run["conversation"],
                exact,
                task.request,
                run["model_calls"],
            )
        else:
            result = await run_planner(
                app.state.agent_model, snapshot, preferences, run["conversation"]
            )
    except asyncio.CancelledError as error:
        cancelled_result = error.result if isinstance(error, PlannerCancelled) else None

        async def save_cancelled():
            async with database.home(home_id, save=False) as (session, _, _engine):
                task = await task_by_id(session, home_id, task_id)
                if cancelled_result is not None:
                    record_round(task, cancelled_result)
                mark_failure(
                    task, "request_cancelled", "请求已中断；本轮未发送设备动作，请只读查看记录"
                )

        await asyncio.shield(save_cancelled())
        raise
    async with database.home(
        home_id, task_id=task_id, save=run.get("strategy") not in EXPERIMENTAL_STRATEGIES
    ) as (session, _, engine):
        task = await task_by_id(session, home_id, task_id)
        updated = record_round(task, result)
        task.updated_at = int(time.time())
        if result["failure_code"]:
            mark_failure(
                task,
                result["failure_code"],
                result.get("failure_message")
                or FAILURE_MESSAGES.get(result["failure_code"], "模型规划未完成，未发送设备动作"),
            )
        elif not same_facts(task, engine):
            mark_failure(task, "state_changed", "规划期间家庭状态或配置已变化，请重新提交")
        else:
            output = result["output"]
            if updated["turn"] == 0 and output["kind"] == "plan":
                output = ambiguous_question(snapshot, task.request["text"]) or output
            try:
                if output["kind"] == "refuse":
                    mark_failure(task, "refused", output["reason"])
                elif output["kind"] == "clarify":
                    validation_started = time.monotonic()
                    options = validate_options(engine, output)
                    updated["question"], updated["options"] = output["question"], options
                    updated["conversation"].append(
                        {
                            "role": "assistant",
                            "text": output["question"],
                            "options": updated["options"],
                        }
                    )
                    task.agent_run = updated
                    add_timing(task, "validation", validation_started)
                    if updated["turn"] >= 3:
                        mark_failure(
                            task, "reply_budget", "补充回答已达三次上限，请重新提交更明确需求"
                        )
                    else:
                        task.status, task.message = "waiting_input", "需要补充信息后继续同一任务"
                else:
                    validation_started = time.monotonic()
                    experimental = updated.get("strategy") in EXPERIMENTAL_STRATEGIES
                    if experimental:
                        optimal = validate_selection(
                            engine, output, updated["goal"], updated["forecast"], task.request
                        )
                        selected_candidate_id = output["candidate_id"]
                        output = output["plan"]
                    plan, confirmation = validate_plan(
                        engine,
                        output,
                        task.request,
                        debug=app.state.settings.simulation_debug_enabled,
                    )
                    task.plan, task.scenario = plan, output["scenario"]
                    if experimental:
                        updated["selected_candidate_id"] = selected_candidate_id
                        updated["preference_optimal"] = optimal
                    updated["proposed_plan"], updated["rationale"] = output, output["rationale"]
                    task.agent_run = updated
                    add_timing(task, "validation", validation_started)
                    if confirmation or experimental:
                        task.status, task.message = (
                            "waiting_confirmation",
                            "请核对实际方案后确认执行",
                        )
                    else:
                        execution_started = time.monotonic()
                        actions = await execute(session, engine, home_id, task_id, plan)
                        task.status, task.message, task.verification = verify(engine, task, actions)
                        add_timing(task, "execution", execution_started)
            except SimulationError as error:
                mark_failure(
                    task,
                    error.code,
                    error.message,
                    diagnostic=getattr(error, "diagnostic", None),
                    public_record=getattr(error, "public_record", None),
                )
        task.final_snapshot = engine.snapshot()
        await session.flush()
        return await detail(session, task)


async def confirm_agent(request, task_id, body, key):
    app, home_id = request.app, request.state.home_id
    database = app.state.database
    digest = request_hash(body.model_dump())
    async with database.sessions() as session:
        task = await task_by_id(session, home_id, task_id)
        if check_replay(task, key, digest, "confirm"):
            return await detail(session, task)
        check_turn(task, body.expected_turn, "waiting_confirmation")
    claim(database, home_id)
    try:
        async with database.home(home_id, task_id=task_id, save=False) as (session, home, engine):
            task = await task_by_id(session, home_id, task_id)
            if check_replay(task, key, digest, "confirm"):
                return await detail(session, task)
            check_turn(task, body.expected_turn, "waiting_confirmation")
            run = deepcopy(task.agent_run)
            operation(run, key, digest, "confirm")
            task.agent_run = run
            if not same_facts(task, engine):
                mark_failure(task, "state_changed", "确认前家庭状态或配置已变化，请重新提交")
            else:
                try:
                    validation_started = time.monotonic()
                    if run.get("strategy") in EXPERIMENTAL_STRATEGIES:
                        validate_selection(
                            engine,
                            dict(
                                kind="selection",
                                candidate_id=run["selected_candidate_id"],
                                plan=run["proposed_plan"],
                            ),
                            run["goal"],
                            run["forecast"],
                            task.request,
                        )
                    plan, _ = validate_plan(
                        engine,
                        run["proposed_plan"],
                        task.request,
                        debug=app.state.settings.simulation_debug_enabled,
                    )
                    task.plan = plan
                    add_timing(task, "validation", validation_started)
                    execution_started = time.monotonic()
                    actions = await execute(session, engine, home_id, task_id, plan)
                    await save_engine(session, home, engine, task_id=task_id)
                    task.status, task.message, task.verification = verify(engine, task, actions)
                    add_timing(task, "execution", execution_started)
                except SimulationError as error:
                    mark_failure(
                        task,
                        error.code,
                        error.message,
                        diagnostic=getattr(error, "diagnostic", None),
                        public_record=getattr(error, "public_record", None),
                    )
            task.final_snapshot = engine.snapshot()
            task.updated_at = int(time.time())
            await session.flush()
            return await detail(session, task)
    finally:
        database.busy.discard(home_id)
