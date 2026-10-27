"""Probe gating/budget tests never read real credentials or call a provider."""

import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "check_model.py"


def probe_module():
    spec = importlib.util.spec_from_file_location("model_probe", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_without_real_flag_does_not_import_provider_or_load_environment():
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"status": "not_run", "model_calls": 0}


def test_probe_never_sends_a_third_model_request():
    module = probe_module()

    class Fake:
        calls = 0

        async def ainvoke(self, messages, tools):
            self.calls += 1
            return "controlled response"

    async def check():
        underlying = Fake()
        bounded = module.BoundedModel(underlying)
        assert await bounded.ainvoke([], []) == "controlled response"
        assert await bounded.ainvoke([], []) == "controlled response"
        with pytest.raises(module.ProbeLimit):
            await bounded.ainvoke([], [])
        assert underlying.calls == bounded.calls == 2

    asyncio.run(check())


def test_probe_does_not_count_an_unexpected_plan_as_clarification_success():
    module = probe_module()
    with pytest.raises(ValueError):
        module.public_result({"output": {"kind": "plan"}, "tool_calls": 1}, 2)


def test_probe_result_excludes_raw_conversation_and_reasoning():
    module = probe_module()
    result = module.public_result(
        {
            "output": {"kind": "clarify", "question": "Choose room"},
            "tool_calls": 1,
            "actual_model": "synthetic-model",
            "usage": None,
            "elapsed_ms": 100,
            "reasoning_content": "synthetic private reasoning",
            "messages": ["synthetic private request"],
        },
        2,
    )
    assert result["status"] == "passed" and result["usage"] is None
    assert "private" not in json.dumps(result)
