"""Explicit browser-test fixture: controlled model + fresh SQLite, never app DB or model API."""

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


class ControlledBrowserModel:
    """Only a deterministic test fixture; not an implementation of language understanding."""

    async def ainvoke(self, messages, tools):
        from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

        reads = [message for message in messages if isinstance(message, ToolMessage)]
        if not reads:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "controlled-read",
                        "name": "read_home",
                        "args": {},
                        "type": "tool_call",
                    }
                ],
            )
        snapshot = json.loads(reads[-1].content)
        requests = [
            json.loads(message.content)["text"]
            for message in messages
            if isinstance(message, HumanMessage)
        ]
        text = requests[-1]
        if text == "受控无效选项诊断":
            output = {
                "kind": "clarify",
                "question": "先确认窗户",
                "options": [{"id": "confirm_closed", "label": "已经关窗", "kind": "entity"}],
            }
        elif len(requests) == 1 and "准备一下" in text:
            output = {
                "kind": "clarify",
                "question": "你希望操作哪个房间？",
                "options": [
                    {"id": room["id"], "label": room["name"], "kind": "room"}
                    for room in snapshot["rooms"]
                ],
            }
        else:
            rooms = (
                snapshot["rooms"]
                if "全屋" in text
                else [
                    next(
                        (
                            room
                            for room in snapshot["rooms"]
                            if room["name"] in text or room["id"] in text
                        ),
                        snapshot["rooms"][0],
                    )
                ]
            )
            ids = [room["id"] for room in rooms]
            future = "回家" in text
            away = "全屋" in text
            actions = []
            for entity in snapshot["entities"]:
                if entity["room_id"] not in ids or not entity["enabled"]:
                    continue
                if entity["type"] == "light":
                    action, parameters = "set_light", {"power": future}
                elif entity["type"] == "climate" and (future or away):
                    action = "set_climate"
                    parameters = (
                        {"mode": "cool", "target_temperature_c": 26, "fan_mode": "auto"}
                        if future
                        else {"mode": "off"}
                    )
                elif entity["type"] == "cover" and future:
                    action, parameters = "set_cover", {"position_pct": 0}
                else:
                    continue
                actions.append(
                    {
                        "entity_id": entity["id"],
                        "room_id": entity["room_id"],
                        "action": action,
                        "parameters": parameters,
                    }
                )
            output = {
                "kind": "plan",
                "scenario": "homecoming" if future else "away" if away else "local",
                "room_ids": ids,
                "keep_entity_ids": [],
                "protected_room_ids": [],
                "actions": actions,
                "temperatures": [{"room_id": ids[0], "target": 26}] if future else [],
                "ready_in_minutes": 60 if future else None,
                "rationale": "可控测试模型方案；不代表真实模型效果",
            }
        return AIMessage(
            content=json.dumps(output, ensure_ascii=False),
            response_metadata={"model_name": "controlled-browser-test"},
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--controlled-sqlite", action="store_true", required=True)
    args = parser.parse_args()
    assert args.controlled_sqlite
    sys.path.insert(0, str(ROOT / "backend" / "src"))
    import uvicorn

    from homemind.app import create_app
    from homemind.config import Settings
    from homemind.persistence.database import Database

    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    database = Database(
        f"sqlite+aiosqlite:///{output / ('product-b-browser-' + uuid4().hex + '.sqlite')}",
        instance_id="controlled-browser-only",
        initialize_test=True,
    )
    app = create_app(
        Settings(
            _env_file=None,
            environment="test",
            database_url=None,
            database_instance_id=None,
            simulation_debug_enabled=True,
            model_enabled=False,
            model_api_key=None,
            allowed_origins=["http://127.0.0.1:5176", "http://localhost:5176"],
        ),
        database=database,
    )
    app.state.agent_model = ControlledBrowserModel()
    uvicorn.run(app, host="127.0.0.1", port=18110, log_level="warning")


if __name__ == "__main__":
    main()
