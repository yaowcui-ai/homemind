"""Fixed follow-up budget, original fixtures and canonical approval; no real API."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "product_eval_d4_followup.py"


def module():
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("product_eval_d4_followup", SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_default_does_not_read_config_or_use_network():
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == dict(status="not_run", targets=3, real_requests=0)


def test_new_budget_is_fixed_24_and_does_not_reuse_original_balance(tmp_path):
    m = module()
    ledger = m.open_budget(tmp_path / "budget.json", resume=False)
    for _ in range(24):
        ledger.reserve("diagnosis/DD01/expert_forecast")
    with pytest.raises(m.d4.base.BudgetExceeded):
        ledger.reserve("repair/DD01/expert_forecast")
    assert m.open_budget(ledger.path, resume=True).used == 24
    with pytest.raises(FileExistsError):
        m.open_budget(ledger.path, resume=False)
    with pytest.raises(ValueError):
        m.validate_batch(tmp_path)


def test_same_original_fixture_and_corrected_keep_approval(tmp_path):
    m = module()
    sys.path.insert(0, str(SCRIPT.parent / "tests"))
    sys.path.insert(0, str(SCRIPT.parents[1] / "backend/src"))
    from test_product_eval_d4 import ControlledD4Model

    case = m.d4.load_cases()[4]
    with m.d4.base.official_http_only():
        original = m.d4.prepare_pair(case, tmp_path / "original")
        frozen = m.frozen_pair(case, tmp_path / "followup", source=tmp_path / "original/pair.json")
        assert frozen["initial_snapshot"] == original["initial_snapshot"]
        result = m.d4.run_trial(
            case, "expert_forecast", frozen, ControlledD4Model(), approve_plan=m.approve_plan
        )
    assert m.audit.audit_score(result)["case_pass"]
    assert result["final_task"]["status"] == "succeeded"
    assert original["template_sha256"] == m.d4.digest(Path(original["template"]).read_bytes())


def test_resume_requires_identical_repair_targets_source_and_model():
    m = module()
    prior = dict(hashes={"agent": "v2"}, model="same", targets=[["DD01", "expert_forecast"]])
    m.validate_resume(prior, {"agent": "v2"}, "same", [("DD01", "expert_forecast")])
    for source, model, targets in [
        ({"agent": "v3"}, "same", [("DD01", "expert_forecast")]),
        ({"agent": "v2"}, "other", [("DD01", "expert_forecast")]),
        ({"agent": "v2"}, "same", [("DD05", "single_forecast")]),
    ]:
        with pytest.raises(ValueError):
            m.validate_resume(prior, source, model, targets)
