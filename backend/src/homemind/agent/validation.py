"""Validate every intent before the shared executor sends its first write."""

from homemind.simulation.models import ControlRequest, EntityType, SimulationError
from homemind.simulation.views import observable


def fail(code, message):
    raise SimulationError(422, code, message)


def validate_options(engine, output):
    result = []
    for option in output["options"]:
        item = (
            engine._room(option["id"]) if option["kind"] == "room" else engine._entity(option["id"])
        )
        result.append({**option, "label": item.name})
    return result


def ambiguous_question(snapshot, text):
    """Catch unresolved literal same-name references before accepting a guessed plan."""
    for kind, items in (("room", snapshot["rooms"]), ("entity", snapshot["entities"])):
        names = {item["name"] for item in items if item["name"] in text}
        for name in names:
            matches = [item for item in items if item["name"] == name]
            if kind == "entity":
                named_rooms = [r["id"] for r in snapshot["rooms"] if r["name"] in text]
                if len(named_rooms) == 1:
                    matches = [item for item in matches if item["room_id"] in named_rooms]
            if len(matches) > 1:
                return {
                    "kind": "clarify",
                    "question": f"有多个“{name}”，请选择具体对象",
                    "options": [
                        {"id": item["id"], "label": item["name"], "kind": kind} for item in matches
                    ],
                }
    return None


def validate_plan(engine, output, request, *, debug):
    room_ids = output["room_ids"]
    keep = output["keep_entity_ids"]
    protected = output["protected_room_ids"]
    for values in (room_ids, keep, protected):
        if len(values) != len(set(values)):
            fail("duplicate_reference", "方案存在重复引用")
    if not set(request["keep_entity_ids"]).issubset(keep) or not set(
        request["protected_room_ids"]
    ).issubset(protected):
        fail("constraint_omitted", "方案遗漏明确指定的保留或保护条件")
    for room_id in room_ids + protected:
        engine._room(room_id)
    for entity_id in keep:
        if not engine._entity(entity_id).enabled:
            fail("disabled_reference", "保留实体未启用")
    if set(room_ids) & set(protected):
        fail("protected_conflict", "目标范围与保护房间冲突")
    scenario = output["scenario"]
    if scenario in {"local", "away"} and (
        output["temperatures"] or output["ready_in_minutes"] is not None
    ):
        fail("invalid_goal", "此场景不接受温度目标或期限")
    if scenario == "homecoming" and (
        output["ready_in_minutes"] is None or not output["temperatures"]
    ):
        fail("invalid_goal", "回家准备需要明确温度目标及仿真提前量")
    if scenario == "sleep" and output["ready_in_minutes"] is not None:
        fail("invalid_goal", "睡眠任务不接受回家期限")
    if scenario in {"homecoming", "sleep"} and len(room_ids) != 1:
        fail("invalid_scope", "回家或睡眠需要恰好一个房间")
    snapshot = engine.snapshot()
    room_views = {room["id"]: room for room in snapshot["rooms"]}
    actions, seen = [], set()
    confirmation = len(room_ids) > 1 or (
        len(output["actions"]) > 1 and set(room_ids + protected) == set(room_views)
    )
    for intent in output["actions"]:
        entity = engine._entity(intent["entity_id"])
        if entity.id in seen:
            fail("duplicate_action", "同一实体不能出现重复或矛盾动作")
        seen.add(entity.id)
        if entity.room_id != intent["room_id"] or entity.room_id not in room_ids:
            fail("invalid_scope", "动作不属于所述房间或目标范围")
        if entity.id in keep or entity.room_id in protected:
            fail("protected_conflict", "动作触及保留实体或受保护房间")
        if not entity.enabled:
            fail("disabled_entity", "动作引用未启用实体")
        if not observable(entity):
            fail("unobservable_entity", "设备离线或读数未知，不能安全执行")
        parameters = engine._validate_control(
            entity, ControlRequest(action=intent["action"], parameters=intent["parameters"])
        )
        if (
            entity.type == EntityType.LIGHT
            and parameters.get("power") is True
            and parameters.get("brightness_pct") == 0
        ):
            fail("contradictory_parameters", "开灯不能同时指定零亮度，未执行任何动作")
        if scenario == "away" and parameters != {
            EntityType.LIGHT: {"power": False},
            EntityType.CLIMATE: {"mode": "off"},
            EntityType.COVER: {"position_pct": 0},
        }.get(entity.type):
            fail("contradictory_scenario", "离家动作必须为关灯、关闭空调或合拢窗帘")
        if entity.type == EntityType.CLIMATE:
            effective_mode = parameters.get("mode", entity.state["mode"])
            if parameters.get("mode") == "off" and any(
                key in parameters for key in ("target_temperature_c", "fan_mode")
            ):
                fail("contradictory_parameters", "关闭空调不能同时修改制冷设置")
            if effective_mode == "cool" and room_views[entity.room_id]["window_open"] is not False:
                fail("window_not_closed", "窗户打开或状态未知，未执行任何动作")
            if entity.state["mode"] == "cool" and any(
                entity.state.get(key) != value for key, value in parameters.items()
            ):
                confirmation = True
        actions.append(
            {
                "entity_id": entity.id,
                "entity_name": entity.name,
                "room_name": engine._room(entity.room_id).name,
                "action": intent["action"],
                "parameters": parameters,
            }
        )
    temperatures, goal_rooms = [], set()
    for goal in output["temperatures"]:
        room_id = goal["room_id"]
        if room_id not in room_ids or room_id in goal_rooms:
            fail("invalid_goal", "温度目标重复或超出范围")
        goal_rooms.add(room_id)
        room = engine._room(room_id)
        sensor = engine._entities.get(room.primary_temperature_entity_id)
        if sensor is None or sensor.type != EntityType.TEMPERATURE or not observable(sensor):
            fail("temperature_unknown", "主温度传感器缺失或未知，无法核验目标")
        cooling = [
            a
            for a in actions
            if a["entity_id"] in {e.id for e in engine._entities.values() if e.room_id == room_id}
            and a["action"] == "set_climate"
            and a["parameters"].get("mode") == "cool"
        ]
        if not cooling or any(
            a["parameters"].get("target_temperature_c") != goal["target"] for a in cooling
        ):
            fail("invalid_goal", "温度目标需要对应相同目标值的制冷动作")
        if not debug and (
            scenario == "homecoming" or room_views[room_id]["temperature_c"] > goal["target"]
        ):
            fail(
                "simulation_debug_required", "此温度目标需要仿真时间推进；请开启演示调试后重新提交"
            )
        temperatures.append({"room_id": room_id, "room_name": room.name, "target": goal["target"]})
    return {
        "actions": actions,
        "constraints": [],
        "temperatures": temperatures,
        "due_at_minutes": engine._minutes + output["ready_in_minutes"]
        if scenario == "homecoming"
        else None,
    }, confirmation
