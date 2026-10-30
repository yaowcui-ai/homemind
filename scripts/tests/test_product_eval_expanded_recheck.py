"""Supplement cannot spend beyond its separate approval or disclose provider bodies."""

import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts/product_eval_expanded_recheck.py"


def module():
    assert SCRIPT.exists()
    spec = importlib.util.spec_from_file_location("expanded_recheck", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_default_is_offline_and_scope_is_four_predeclared_runs():
    m = module()
    response = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert response.returncode == 0
    assert json.loads(response.stdout)["real_requests"] == 0
    assert len(set(m.TARGETS)) == 4
    assert {c for c, _ in m.TARGETS} == {"X21", "X24"}


def test_supplement_limit_and_parent_total_are_independent(tmp_path):
    m = module()
    ledger = m.open_budget(tmp_path / "budget.json", "fixed", parent_used=350, resume=False)
    for _ in range(10):
        ledger.reserve("approved")
    with pytest.raises(m.e.d5.d4.base.BudgetExceeded):
        ledger.reserve("blocked")
    assert ledger.used == 10


def test_provider_failure_diagnostics_record_only_safe_status(tmp_path):
    m = module()
    from homemind.agent.model import ModelFailure

    ledger = m.open_budget(tmp_path / "budget.json", "fixed", parent_used=284, resume=False)

    class FailedModel:
        async def ainvoke(self, _messages, _tools):
            raise ModelFailure("model_unavailable", http_status=503)

    model = m.DiagnosticModel(FailedModel(), ledger)
    model.case_id = "X24"
    with pytest.raises(ModelFailure):
        asyncio.run(model.ainvoke([], []))
    record = json.loads(ledger.path.read_text(encoding="utf-8"))["requests"][0]
    assert record["http_status"] == 503
    assert record["failure_code"] == "model_unavailable"
    assert set(record) == {
        "number",
        "case_id",
        "outcome",
        "http_status",
        "failure_code",
        "transport_error",
    }
