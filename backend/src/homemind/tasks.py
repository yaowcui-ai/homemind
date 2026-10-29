"""Inline, idempotent household tasks; no background scheduling or model calls."""

import hashlib
import json
import time
from copy import deepcopy
from uuid import uuid4

from fastapi import APIRouter, Header, Request
from pydantic import Field
from sqlalchemy import select

from homemind.auth import EmptyBody, require_home
from homemind.executor import execute, verify
from homemind.persistence.codec import save_engine
from homemind.persistence.models import Action, Preference, Task
from homemind.preferences import preference_view
from homemind.rules import RuleRequest, normalize, plan_rules
from homemind.simulation.models import Identifier, InputModel, SimulationError


class AdvanceRequest(InputModel):
    expected_world_id: Identifier
    expected_simulated_minutes: int = Field(ge=0, strict=True)


def advance_replay(task, key, body):
    for record in task.advance_records or []:
        if record["key"] == key:
            if record["request_hash"] != request_hash(body):
                raise SimulationError(409, "idempotency_conflict", "此推进键已用于不同请求")
            return record["result"]
    return None


def request_hash(request):
    return hashlib.sha256(
        json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def replay(task, body):
    if task.mode != "rule":
        raise SimulationError(409, "idempotency_conflict", "此幂等键已用于不同任务模式")
    normalized = normalize(body, task.preferences_snapshot)
    if request_hash(normalized) != task.request_hash:
        raise SimulationError(409, "idempotency_conflict", "此幂等键已用于不同请求，请更换幂等键")


def summary(task):
    return {
        key: getattr(task, key)
        for key in (
            "id",
            "mode",
            "scenario",
            "status",
            "created_at",
            "updated_at",
            "world_id",
            "message",
        )
    }


async def detail(session, task):
    actions = await session.scalars(
        select(Action)
        .where(Action.home_id == task.home_id, Action.task_id == task.id)
        .order_by(Action.sequence)
    )
    return {
        **summary(task),
        **{
            key: getattr(task, key)
            for key in (
                "request",
                "preferences_snapshot",
                "initial_snapshot",
                "final_snapshot",
                "plan",
                "agent_run",
            )
        },
        "verification": task.verification
        or {
            "due_at_minutes": task.plan.get("due_at_minutes"),
            "checked_at_minutes": task.final_snapshot["simulated_minutes"],
            "conditions": [],
        },
        "actions": [
            {
                key: getattr(action, key)
                for key in (
                    "id",
                    "entity_id",
                    "entity_name",
                    "room_name",
                    "action",
                    "parameters",
                    "status",
                    "transport_outcome",
                    "message",
                )
            }
            for action in actions
        ],
        "advance_records": [
            {key: record[key] for key in ("key", "request", "advanced_to_minutes")}
            for record in task.advance_records or []
        ],
    }


async def task_by_id(session, home_id, task_id):
    task = await session.scalar(select(Task).where(Task.home_id == home_id, Task.id == task_id))
    if task is None:
        raise SimulationError(404, "not_found", "找不到任务")
    return task


def tasks_router():
    router = APIRouter(prefix="/tasks", tags=["tasks"])

    @router.post("")
    async def create(
        body: RuleRequest,
        request: Request,
        idempotency_key: str = Header(pattern=r"^[A-Za-z0-9._:-]{8,128}$"),
    ):
        home_id = require_home(request)
        database = request.app.state.database
        # A committed replay is resolved before the occupancy check. Stored preferences
        # make omitted defaults stable even when the user later edits preferences.
        async with database.sessions() as session:
            previous = await session.scalar(
                select(Task).where(Task.home_id == home_id, Task.idempotency_key == idempotency_key)
            )
            if previous:
                replay(previous, body)
                return await detail(session, previous)
        if home_id in database.busy:
            raise SimulationError(409, "home_busy", "当前家庭正在执行规则任务，请稍后重试")
        database.busy.add(home_id)
        task_id = uuid4().hex
        try:
            async with database.home(home_id, task_id=task_id) as (session, _, engine):
                # Recheck after acquiring the per-home and database row locks.
                previous = await session.scalar(
                    select(Task).where(
                        Task.home_id == home_id, Task.idempotency_key == idempotency_key
                    )
                )
                if previous:
                    replay(previous, body)
                    return await detail(session, previous)
                preferences = preference_view(await session.get(Preference, home_id))
                normalized = normalize(body, preferences)
                plan = plan_rules(engine, normalized, preferences)
                if not request.app.state.settings.simulation_debug_enabled:
                    rooms = {room["id"]: room for room in engine.snapshot()["rooms"]}
                    needs_clock = plan["due_at_minutes"] is not None or any(
                        rooms[goal["room_id"]]["temperature_c"] is None
                        or rooms[goal["room_id"]]["temperature_c"] > goal["target"]
                        for goal in plan["temperatures"]
                    )
                    if needs_clock:
                        raise SimulationError(
                            422,
                            "simulation_debug_required",
                            "此温度目标需要仿真时间推进；请开启演示调试后重新提交",
                        )
                now = int(time.time())
                initial = engine.snapshot()
                task = Task(
                    id=task_id,
                    home_id=home_id,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash(normalized),
                    request=normalized,
                    scenario=body.scenario,
                    status="running",
                    world_id=engine._world_id,
                    initial_snapshot=initial,
                    preferences_snapshot=preferences,
                    plan=plan,
                    final_snapshot=initial,
                    verification={},
                    message="正在执行规则任务",
                    created_at=now,
                    updated_at=now,
                )
                session.add(task)
                await session.flush()
                actions = await execute(session, engine, home_id, task.id, plan)
                task.status, task.message, task.verification = verify(engine, task, actions)
                task.final_snapshot = engine.snapshot()
                await session.flush()
                return await detail(session, task)
        finally:
            database.busy.discard(home_id)

    @router.get("")
    async def list_tasks(request: Request, submission_key: str | None = None):
        home_id = require_home(request)
        async with request.app.state.database.sessions() as session:
            query = select(Task).where(Task.home_id == home_id)
            if submission_key is not None:
                query = query.where(Task.idempotency_key == submission_key)
            tasks = await session.scalars(
                query.order_by(Task.created_at.desc(), Task.id.desc()).limit(50)
            )
            return [summary(task) for task in tasks]

    @router.get("/{task_id}")
    async def get_task(task_id: str, request: Request):
        home_id = require_home(request)
        async with request.app.state.database.sessions() as session:
            return await detail(session, await task_by_id(session, home_id, task_id))

    @router.post("/{task_id}/verify")
    async def verify_task(task_id: str, body: EmptyBody, request: Request):
        home_id = require_home(request)
        async with request.app.state.database.home(home_id, save=False) as (session, _, engine):
            task = await task_by_id(session, home_id, task_id)
            if task.status == "succeeded":
                # Completed task facts describe their completion instant. Later
                # household controls/reset cannot rewrite that historical result.
                return await detail(session, task)
            actions = list(
                await session.scalars(
                    select(Action)
                    .where(Action.home_id == home_id, Action.task_id == task_id)
                    .order_by(Action.sequence)
                )
            )
            if (task.mode in {"single_agent", "multi_agent"} and not actions) or task.status in {
                "planning",
                "waiting_input",
                "waiting_confirmation",
            }:
                return await detail(session, task)
            task.status, task.message, task.verification = verify(engine, task, actions)
            task.final_snapshot = engine.snapshot()
            task.updated_at = int(time.time())
            await session.flush()
            return await detail(session, task)

    @router.post("/{task_id}/advance")
    async def advance_task(
        task_id: str,
        body: AdvanceRequest | EmptyBody,
        request: Request,
        idempotency_key: str | None = Header(default=None, pattern=r"^[A-Za-z0-9._:-]{8,128}$"),
    ):
        home_id = require_home(request)
        protected = isinstance(body, AdvanceRequest)
        if protected != (idempotency_key is not None):
            raise SimulationError(
                422, "invalid_request", "受保护推进必须同时提供世界、时刻及幂等键"
            )
        normalized = body.model_dump()
        if not request.app.state.settings.simulation_debug_enabled:
            raise SimulationError(403, "simulation_debug_disabled", "任务时间推进仅限仿真调试模式")
        database = request.app.state.database
        if protected:
            async with database.sessions() as session:
                task = await task_by_id(session, home_id, task_id)
                previous = advance_replay(task, idempotency_key, normalized)
                if previous is not None:
                    return previous
        if home_id in database.busy:
            raise SimulationError(409, "home_busy", "当前家庭正在处理任务")
        database.busy.add(home_id)
        try:
            async with database.home(home_id, save=False) as (session, home, engine):
                task = await task_by_id(session, home_id, task_id)
                if protected:
                    previous = advance_replay(task, idempotency_key, normalized)
                    if previous is not None:
                        return previous
                    if body.expected_world_id != engine._world_id:
                        raise SimulationError(409, "world_changed", "环境已重置，请重新读取家庭")
                    if body.expected_simulated_minutes != engine._minutes:
                        raise SimulationError(
                            409, "clock_changed", "仿真时刻已变化，请读取当前状态后再决定推进"
                        )
                    if len(task.advance_records or []) >= 256:
                        raise SimulationError(
                            409, "advance_limit", "此任务已达推进次数上限，请读取目标状态"
                        )
                actions = list(
                    await session.scalars(
                        select(Action)
                        .where(Action.home_id == home_id, Action.task_id == task_id)
                        .order_by(Action.sequence)
                    )
                )
                if task.world_id != engine._world_id:
                    raise SimulationError(409, "world_changed", "环境已重置，旧任务不可推进")
                if not actions or task.status not in {"waiting_verification", "partial"}:
                    raise SimulationError(
                        409, "task_not_continuable", "此任务没有已执行的可继续目标"
                    )
                due = task.plan["due_at_minutes"]
                if due is not None:
                    if due <= engine._minutes:
                        raise SimulationError(
                            409, "deadline_passed", "已到达或错过目标时刻，不可补造历史证据"
                        )
                    minutes = due - engine._minutes
                elif task.scenario == "sleep" and task.plan["temperatures"]:
                    minutes = 10
                else:
                    raise SimulationError(409, "task_not_continuable", "此任务没有待推进的温度目标")
                engine.advance(minutes)
                task.status, task.message, task.verification = verify(engine, task, actions)
                task.final_snapshot = engine.snapshot()
                task.updated_at = int(time.time())
                if protected:
                    record = {
                        "key": idempotency_key,
                        "request": normalized,
                        "request_hash": request_hash(normalized),
                        "advanced_to_minutes": engine._minutes,
                    }
                    # Public details omit stored results, so snapshots never recursively nest.
                    result = deepcopy(await detail(session, task))
                    result["advance_records"].append(
                        {key: record[key] for key in ("key", "request", "advanced_to_minutes")}
                    )
                    record["result"] = result
                    task.advance_records = [*(task.advance_records or []), record]
                await save_engine(session, home, engine, task_id=task_id)
                await session.flush()
                return await detail(session, task)
        finally:
            database.busy.discard(home_id)

    return router
