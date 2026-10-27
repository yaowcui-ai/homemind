"""Inline, idempotent household tasks; no background scheduling or model calls."""

import hashlib
import json
import time
from uuid import uuid4

from fastapi import APIRouter, Header, Request
from sqlalchemy import select

from homemind.auth import EmptyBody, require_home
from homemind.executor import execute, verify
from homemind.persistence.models import Action, Preference, Task
from homemind.preferences import preference_view
from homemind.rules import RuleRequest, normalize, plan_rules
from homemind.simulation.models import SimulationError


def request_hash(request):
    return hashlib.sha256(
        json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def replay(task, body):
    normalized = normalize(body, task.preferences_snapshot)
    if request_hash(normalized) != task.request_hash:
        raise SimulationError(409, "idempotency_conflict", "此幂等键已用于不同请求，请更换幂等键")


def summary(task):
    return {
        key: getattr(task, key)
        for key in ("id", "scenario", "status", "created_at", "updated_at", "world_id", "message")
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
                "verification",
            )
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
    async def list_tasks(request: Request):
        home_id = require_home(request)
        async with request.app.state.database.sessions() as session:
            tasks = await session.scalars(
                select(Task)
                .where(Task.home_id == home_id)
                .order_by(Task.created_at.desc(), Task.id.desc())
                .limit(50)
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
            task.status, task.message, task.verification = verify(engine, task, actions)
            task.final_snapshot = engine.snapshot()
            task.updated_at = int(time.time())
            await session.flush()
            return await detail(session, task)

    return router
