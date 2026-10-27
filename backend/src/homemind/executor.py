"""Absolute local simulation actions and independent observation verification."""

from decimal import Decimal
from uuid import uuid4

from homemind.persistence.models import Action
from homemind.simulation.models import ControlRequest, EntityType, SimulationError
from homemind.simulation.views import entity_view, observable


def read_action(engine, action):
    entity = engine._entities.get(action.entity_id)
    if entity is None or entity.archived:
        return "failed", "实体已归档或不存在", {}
    if not observable(entity):
        return "unknown", "独立读数不可用，无法确认动作", entity_view(entity)
    matches = all(entity.state.get(key) == value for key, value in action.parameters.items())
    if not matches and entity.pending:
        return "pending", "延迟动作尚未生效", entity_view(entity)
    if not matches:
        return "failed", "独立读回未满足动作条件", entity_view(entity)
    return "verified", "已通过独立读回核验", entity_view(entity)


async def execute(session, engine, home_id, task_id, plan):
    actions = []
    for sequence, intent in enumerate(plan["actions"]):
        action = Action(
            id=uuid4().hex,
            home_id=home_id,
            task_id=task_id,
            sequence=sequence,
            **intent,
            status="planned",
            transport_outcome=None,
            message="动作意图已记录",
            readback={},
        )
        session.add(action)
        await session.flush()
        try:
            result = engine.control(
                action.entity_id,
                ControlRequest(
                    action=action.action,
                    parameters=action.parameters,
                    expected_world_id=engine._world_id,
                ),
            )
            action.transport_outcome = result["outcome"]
            action.message = result["message"]
        except SimulationError as error:
            action.transport_outcome = "failed"
            action.message = error.message
        outcome, message, reading = read_action(engine, action)
        action.readback = reading
        if action.transport_outcome == "failed":
            action.status = "failed"
        else:
            action.status = "unknown" if outcome in {"pending", "unknown"} else outcome
            action.message = message
        actions.append(action)
    return actions


def verify(engine, task, actions):
    if task.world_id != engine._world_id:
        return (
            "failed",
            "仿真环境已重置，旧任务不可在新环境执行",
            {
                "due_at_minutes": task.plan["due_at_minutes"],
                "checked_at_minutes": engine._minutes,
                "conditions": [
                    {
                        "label": "环境版本",
                        "outcome": "failed",
                        "message": "仿真环境已重置，旧任务条件已失效；未重新发送动作",
                    }
                ],
            },
        )
    conditions = list(task.plan["constraints"])
    original_rooms = {
        entity["id"]: entity["room_id"] for entity in task.initial_snapshot["entities"]
    }
    for action in actions:
        outcome, message, reading = read_action(engine, action)
        current = engine._entities.get(action.entity_id)
        if current is not None and current.room_id != original_rooms.get(action.entity_id):
            outcome, message = "failed", "实体已迁移房间，旧范围条件不再成立"
        if action.transport_outcome == "failed":
            outcome, message = "failed", action.message
        new_status = "unknown" if outcome in {"pending", "unknown"} else outcome
        # Preserve immutable evidence when nothing changed; verify never sends controls.
        if action.status != new_status or action.readback != reading:
            action.status, action.message, action.readback = new_status, message, reading
        conditions.append(
            {
                "label": f"{action.room_name} / {action.entity_name}",
                "outcome": outcome,
                "message": message,
            }
        )
    due = task.plan["due_at_minutes"]
    early = due is not None and engine._minutes < due
    deadline_evidence = dict(task.plan.get("deadline_evidence", {}))
    for target in task.plan["temperatures"]:
        room = engine._rooms.get(target["room_id"])
        sensor = engine._entities.get(room.primary_temperature_entity_id) if room else None
        label = f"{target['room_name']} / 温度 ≤ {target['target']}°C"
        if due is not None and engine._minutes >= due:
            evidence = deadline_evidence.get(target["room_id"])
        else:
            evidence = None
        if evidence is not None:
            outcome, message = evidence["outcome"], evidence["message"]
        elif due is not None and engine._minutes > due:
            outcome = "unknown"
            message = "已超过目标时刻，缺少该时刻读数，无法确认按时达标"
        elif sensor is None or sensor.type != EntityType.TEMPERATURE or not observable(sensor):
            outcome, message = "unknown", "主温度读数未知，不能确认目标达成"
        elif early:
            outcome, message = "pending", "目标时刻尚未到达，需要推进时间后核验"
        elif Decimal(str(sensor.state["temperature_c"])) <= Decimal(target["target"]):
            outcome = "verified"
            message = "当前独立温度读数已达标" if due is None else "目标时刻独立温度读数已达标"
        elif due is None:
            outcome, message = "pending", "睡眠温度尚未达标，需要推进时间后核验"
        else:
            outcome, message = "failed", "目标时刻独立温度读数未达标"
        if (
            due is not None
            and engine._minutes == due
            and target["room_id"] not in deadline_evidence
        ):
            # Historical deadline evidence is distinct from the latest readback. It
            # survives later verifies/restarts; no scheduler or implicit clock advance.
            deadline_evidence[target["room_id"]] = {
                "checked_at_minutes": due,
                "sensor_id": sensor.id if sensor else None,
                "temperature_c": (
                    sensor.state["temperature_c"] if sensor and observable(sensor) else None
                ),
                "outcome": outcome,
                "message": message,
            }
        conditions.append({"label": label, "outcome": outcome, "message": message})
    if due is not None and engine._minutes == due:
        task.plan = {**task.plan, "deadline_evidence": deadline_evidence}
    outcomes = [condition["outcome"] for condition in conditions]
    if any(outcome in {"failed", "unknown"} for outcome in outcomes):
        status = "partial" if any(outcome == "verified" for outcome in outcomes) else "failed"
        message = "部分条件失败或无法确认，请查看逐项核验"
    elif early or "pending" in outcomes:
        status, message = "waiting_verification", "动作已处理，目标条件仍等待核验"
    else:
        status, message = "succeeded", "全部必需动作和目标条件已核验通过"
    return (
        status,
        message,
        {"due_at_minutes": due, "checked_at_minutes": engine._minutes, "conditions": conditions},
    )
