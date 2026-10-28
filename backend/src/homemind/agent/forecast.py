"""Bounded, exact-state simulation on private clones; no public-state reconstruction."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from decimal import Decimal
from threading import BoundedSemaphore, Event

from homemind.agent.schemas import GoalContract
from homemind.simulation.models import ControlRequest, EntityType, FaultMode, SimulationError
from homemind.simulation.physics import energy_wh
from homemind.simulation.service import SimulationService
from homemind.simulation.views import observable

MAX_ROOMS = 16
MAX_ENTITIES = 256
MAX_ARCHIVES = 256
_workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="homemind-forecast")
_slots = BoundedSemaphore(2)


def unavailable(message):
    raise SimulationError(422, "forecast_unavailable", message)


def clone_engine(engine):
    """Copy domain records under the source lock, constructing a separate fresh RLock."""
    with engine._lock:
        if (
            len(engine._rooms) > MAX_ROOMS
            or len(engine._entities) > MAX_ENTITIES
            or len(engine._archives) > MAX_ARCHIVES
        ):
            unavailable("家庭规模超过预测上限（16房间、256实体或256归档），请缩小配置")
        result = SimulationService(engine._home_id, seed=False)
        for key in (
            "_rooms",
            "_entities",
            "_world_id",
            "_revision",
            "_config_revision",
            "_minutes",
            "_event_sequence",
            "_events",
            "_new_events",
            "_archives",
        ):
            setattr(result, key, deepcopy(getattr(engine, key)))
        return result


def validate_goal(engine, goal, request):
    """Reject unsupported/invalid references without returning or storing their values."""
    goal = GoalContract.model_validate(goal).model_dump()
    if goal["room_id"] not in engine._rooms:
        unavailable("目标房间不属于当前家庭")
    for field, collection in (
        ("keep_entity_ids", engine._entities),
        ("protected_room_ids", engine._rooms),
    ):
        if not set(request.get(field, [])).issubset(goal[field]):
            raise SimulationError(
                422, "constraint_omitted", "目标遗漏表单中明确指定的保留或保护条件"
            )
        if any(
            i not in collection or getattr(collection[i], "archived", False) for i in goal[field]
        ):
            unavailable("保留或保护对象不属于当前家庭")
    room_id = goal["room_id"]
    entities = [
        e
        for e in engine._entities.values()
        if e.room_id == room_id and e.enabled and not e.archived
    ]
    climates = [e for e in entities if e.type == EntityType.CLIMATE]
    covers = [e for e in entities if e.type == EntityType.COVER]
    if len(climates) != 1 or len(covers) > 1:
        unavailable("目标房间须恰好一台已启用空调且至多一只窗帘，多实例暂不支持预测")
    if (
        climates[0].id != goal["climate_entity_id"]
        or (covers[0].id if covers else None) != goal["cover_entity_id"]
    ):
        unavailable("目标空调或窗帘与房间实际配置不一致")
    if room_id in goal["protected_room_ids"] or climates[0].id in goal["keep_entity_ids"]:
        unavailable("目标温控与保留或房间保护条件冲突，请明确放宽哪项要求")
    if covers and covers[0].id in goal["keep_entity_ids"] and goal["cover_constraint"] != "keep":
        raise SimulationError(422, "constraint_omitted", "保留窗帘时目标必须固定窗帘位置")
    room = engine._rooms[room_id]
    sensor = engine._entities.get(room.primary_temperature_entity_id)
    if (
        sensor is None
        or sensor.type != EntityType.TEMPERATURE
        or sensor.room_id != room_id
        or not observable(sensor)
    ):
        unavailable("主温度感知缺失或不可观测，无法预测达标时间")
    inputs = []
    for kind in (EntityType.WINDOW, EntityType.OCCUPANCY):
        signals = [e for e in entities if e.type == kind]
        if not signals or any(not observable(e) for e in signals):
            unavailable("所有参与物理过程的窗户和占用感知须存在且可观测")
        inputs.extend(signals)
    if any(
        not observable(e) or e.fault_mode != FaultMode.NONE or e.pending is not None
        for e in [sensor] + climates + covers + inputs
    ):
        unavailable("参与预测的设备或物理输入有故障、未知或待执行动作，暂不能确定预测")
    if any(e.state["window_open"] for e in inputs if e.type == EntityType.WINDOW):
        unavailable("窗户打开时不能安全规划制冷，请先确认关闭窗户")
    return goal


def forecast_plan(engine, goal, *, cancel=None, deadline=None):
    """All actions and 1-minute replay affect clones only; each candidate starts fresh."""
    goal = validate_goal(engine, goal, {})
    frozen = clone_engine(engine)
    source = frozen.snapshot()
    scope = [goal["climate_entity_id"]] + (
        [goal["cover_entity_id"]] if goal["cover_entity_id"] else []
    )
    cover = frozen._entities.get(goal["cover_entity_id"])
    positions = (
        ([cover.state["position_pct"]] if goal["cover_constraint"] == "keep" else [0, 100])
        if cover
        else [None]
    )
    candidates = []

    def check_stop():
        if cancel is not None and cancel.is_set():
            unavailable("预测计算已取消，未发送任何设备动作")
        if deadline is not None and time.monotonic() >= deadline:
            raise SimulationError(422, "round_timeout", "预测超出本轮时间预算，未发送任何设备动作")

    for fan in (f for f in ("low", "auto") if f in goal["allowed_fan_modes"]):
        for position in positions:
            check_stop()
            clone = clone_engine(frozen)
            baseline = sum((clone._entities[i].energy_watt_minutes for i in scope), Decimal(0))
            actions = [
                dict(
                    entity_id=goal["climate_entity_id"],
                    room_id=goal["room_id"],
                    action="set_climate",
                    parameters=dict(
                        mode="cool", fan_mode=fan, target_temperature_c=goal["target_temperature_c"]
                    ),
                )
            ]
            if cover and goal["cover_constraint"] != "keep":
                actions.append(
                    dict(
                        entity_id=cover.id,
                        room_id=goal["room_id"],
                        action="set_cover",
                        parameters={"position_pct": position},
                    )
                )
            for action in actions:
                clone.control(
                    action["entity_id"],
                    ControlRequest(action=action["action"], parameters=action["parameters"]),
                )
            sensor_id = clone._rooms[goal["room_id"]].primary_temperature_entity_id

            def temperature():
                from homemind.simulation.views import entity_view

                return entity_view(clone._entities[sensor_id])["state"]["temperature_c"]

            first = 0 if temperature() <= goal["target_temperature_c"] else None
            for minute in range(1, goal["ready_in_minutes"] + 1):
                check_stop()
                clone.advance(1)
                if first is None and temperature() <= goal["target_temperature_c"]:
                    first = minute
            check_stop()
            end = temperature()
            candidates.append(
                dict(
                    id=f"c{len(candidates) + 1}",
                    fan_mode=fan,
                    cover_position_pct=position,
                    end_temperature_c=end,
                    first_observed_goal_minute=first,
                    deadline_met=end <= goal["target_temperature_c"],
                    energy_wh=energy_wh(
                        sum((clone._entities[i].energy_watt_minutes for i in scope), Decimal(0))
                        - baseline
                    ),
                    actions=actions,
                )
            )
    return dict(
        model_version=source["model_version"],
        source={
            k: source[k] for k in ("world_id", "revision", "config_revision", "simulated_minutes")
        },
        energy_scope_entity_ids=scope,
        candidates=candidates,
    )


async def run_forecast(engine, goal, deadline):
    """A slot is owned by the actual worker until its finally block completes."""
    if not _slots.acquire(blocking=False):
        unavailable("预测计算正在处理其他任务，请稍后重试")
    cancel = Event()

    def work():
        try:
            return forecast_plan(engine, goal, cancel=cancel, deadline=deadline)
        finally:
            _slots.release()

    try:
        future = _workers.submit(work)
    except BaseException:
        _slots.release()
        raise
    wrapped = asyncio.wrap_future(future)
    # Consume eventual worker exceptions even if its awaiting request has ended.
    wrapped.add_done_callback(lambda f: None if f.cancelled() else f.exception())
    try:
        return await asyncio.wait_for(asyncio.shield(wrapped), max(0, deadline - time.monotonic()))
    except (asyncio.CancelledError, TimeoutError):
        cancel.set()
        raise


def validate_selection(engine, selection, goal, forecast, request):
    validate_goal(engine, goal, request)
    current = engine.snapshot()
    if forecast["model_version"] != current["model_version"] or any(
        forecast["source"][key] != current[key] for key in forecast["source"]
    ):
        raise SimulationError(422, "state_changed", "预测依据已变化，请重新提交")
    candidate = next(
        (c for c in forecast["candidates"] if c["id"] == selection["candidate_id"]), None
    )
    if candidate is None or not candidate["deadline_met"]:
        raise SimulationError(422, "invalid_selection", "选择不存在或不满足硬期限的候选，未执行")
    plan = selection["plan"]
    if (
        plan["scenario"] != "homecoming"
        or plan["room_ids"] != [goal["room_id"]]
        or plan["temperatures"]
        != [dict(room_id=goal["room_id"], target=goal["target_temperature_c"])]
        or plan["ready_in_minutes"] != goal["ready_in_minutes"]
        or set(plan["keep_entity_ids"]) != set(goal["keep_entity_ids"])
        or set(plan["protected_room_ids"]) != set(goal["protected_room_ids"])
        or sorted(plan["actions"], key=lambda a: a["entity_id"])
        != sorted(candidate["actions"], key=lambda a: a["entity_id"])
    ):
        raise SimulationError(422, "goal_drift", "方案动作、目标、期限或保留条件与目标及候选不一致")
    feasible = [c for c in forecast["candidates"] if c["deadline_met"]]

    def score(c):
        values = (c["first_observed_goal_minute"], c["energy_wh"])
        return values if goal["priority"] == "comfort_first" else values[::-1]

    return score(candidate) == min(map(score, feasible))
