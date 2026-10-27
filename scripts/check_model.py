"""Opt-in, at most two synthetic DeepSeek requests; no household DB or device writes."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ProbeLimit(Exception):
    """A third request is forbidden even if the planner requests it."""


class BoundedModel:
    def __init__(self, model):
        self.model = model
        self.calls = 0

    async def ainvoke(self, messages, tools):
        if self.calls >= 2:
            raise ProbeLimit()
        self.calls += 1
        return await self.model.ainvoke(messages, tools)


def public_result(result, calls):
    output = result["output"]
    if hasattr(output, "model_dump"):
        output = output.model_dump()
    if output.get("kind") != "clarify" or result.get("tool_calls", 0) < 1:
        raise ValueError("Expected a validated clarification after a real read tool call")
    return {
        "status": "passed",
        "scope": "synthetic_tool_and_clarification_only",
        "model_calls": calls,
        "tool_calls": result["tool_calls"],
        "actual_model": result.get("actual_model"),
        "usage": result.get("usage"),
        "elapsed_ms": result.get("elapsed_ms"),
        "output_kind": "clarify",
        "device_actions": 0,
    }


async def run_real():
    # Imports and configuration loading happen only after explicit --real.
    sys.path.insert(0, str(ROOT / "backend" / "src"))
    from dotenv import dotenv_values
    from homemind.agent.graph import run_planner
    from homemind.agent.model import DeepSeekModel
    from homemind.config import Settings
    from homemind.simulation.service import SimulationService

    local = dotenv_values(ROOT / "backend" / ".env")
    config = Settings(
        _env_file=None,
        model_enabled=str(local.get("HOMEMIND_MODEL_ENABLED", "false")).lower() == "true",
        model_provider=local.get("HOMEMIND_MODEL_PROVIDER", "deepseek"),
        model_name=local.get("HOMEMIND_MODEL_NAME", "deepseek-flash"),
        model_base_url=local.get("HOMEMIND_MODEL_BASE_URL", "https://api.deepseek.com"),
        model_api_key=local.get("HOMEMIND_MODEL_API_KEY") or None,
    )
    if not config.model_enabled or not config.model_api_key:
        print(json.dumps({"status": "not_configured", "model_calls": 0}))
        return 1
    bounded = BoundedModel(DeepSeekModel(config))
    # This world exists only in this process; it is never loaded from MySQL.
    snapshot = SimulationService().snapshot()
    for room in snapshot["rooms"]:
        room["name"] = "客厅"
    preferences = {
        "version": 1,
        "comfort_temperature_c": 26,
        "sleep_temperature_c": 27,
        "fan_mode": "low",
        "arrival_lead_minutes": 60,
    }
    try:
        result = await run_planner(
            bounded,
            snapshot,
            preferences,
            [
                {
                    "role": "user",
                    "text": "关闭客厅主灯。请先读取家庭事实；"
                    "若房间同名，请问我选哪间，不能任意选择。",
                }
            ],
        )
        print(json.dumps(public_result(result, bounded.calls), ensure_ascii=True))
        return 0
    except Exception:
        # Provider diagnostics can contain request data; never print their text/trace.
        print(
            json.dumps(
                {"status": "failed", "code": "probe_not_passed", "model_calls": bounded.calls}
            )
        )
        return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true", help="Allow at most 2 real model requests")
    args = parser.parse_args()
    if not args.real:
        print(json.dumps({"status": "not_run", "model_calls": 0}))
        return 0
    try:
        return asyncio.run(run_real())
    except Exception:
        print(json.dumps({"status": "failed", "code": "probe_setup_failed", "model_calls": 0}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
