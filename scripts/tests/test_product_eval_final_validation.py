"""The final fresh set has an independent ceiling and cannot replay stopped work."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts/product_eval_final_validation.py"


def module():
    assert SCRIPT.exists()
    spec = importlib.util.spec_from_file_location("final_validation", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_default_offline_and_fresh_balanced_schedule():
    m = module()
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)["real_requests"] == 0
    cases = m.load_cases()
    assert len(cases) == 12
    assert len({c["id"] for c in cases}) == 12
    assert all(c["id"].startswith("Z") for c in cases)
    assert (
        sorted([c["family"] for c in cases].count(f) for f in {c["family"] for c in cases})
        == [2] * 6
    )
    assert len(set(m.schedule())) == 24


def test_parent_total_and_new_scope_both_enforced(tmp_path):
    m = module()
    ledger = m.open_budget(tmp_path / "budget.json", "fixed", parent_used=358, resume=False)
    ledger.reserve("a")
    ledger.reserve("b")
    with pytest.raises(m.e.d5.d4.base.BudgetExceeded):
        ledger.reserve("c")


def test_scope_restored_and_final_journey_can_start_with_exact_headroom():
    m = module()
    old = m.e.BATCH, m.e.CASES
    with pytest.raises(RuntimeError), m.scope():
        assert m.e.BATCH == m.BATCH
        raise RuntimeError("stop")
    assert (m.e.BATCH, m.e.CASES) == old
    assert m.required_requests({"reply": "25℃"}, "expert_forecast") == 5
    assert m.required_requests({"reply": "25℃"}, "single_forecast") == 3


def test_changed_source_or_parent_is_rejected_before_model_configuration(monkeypatch):
    m = module()
    monkeypatch.setattr(m, "frozen_manifest", lambda: {"source_hashes": {"old": "hash"}})
    with pytest.raises(ValueError, match="frozen_final_source_or_parent_changed"):
        m.validate()
