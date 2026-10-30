"""Budget, comparison design and no-network defaults for the quality batch."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "product_eval_quality.py"
sys.path.insert(0, str(SCRIPT.parent))


def module():
    spec = importlib.util.spec_from_file_location("product_eval_quality", SCRIPT)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_default_is_offline_and_does_not_open_credential_configuration():
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == dict(
        status="not_run",
        development_runs=24,
        new_case_runs=8,
        limit=80,
        real_requests=0,
    )


def test_design_contains_every_revision_strategy_pair_and_new_cases_once():
    m = module()
    schedule = m.schedule()
    assert len(schedule) == len(set(schedule)) == 32
    development = [r for r in schedule if r[0] in m.DEVELOPMENT]
    assert len(development) == 24
    for case in m.DEVELOPMENT:
        assert {(revision, strategy) for c, revision, strategy in development if c == case} == {
            (revision, strategy)
            for revision in ("baseline", "candidate")
            for strategy in m.d5.d4.STRATEGIES
        }
    assert all(revision == "candidate" for case, revision, _ in schedule if case.startswith("Q"))


def test_stop_before_next_round_and_never_reuse_old_budget(tmp_path):
    m = module()
    ledger = m.open_budget(tmp_path / "budget.json", "fixed-scope", resume=False)
    for i in range(75):
        ledger.reserve("issued")
    assert not m.can_start(ledger)
    assert ledger.used == 75
    with pytest.raises(ValueError):
        m.open_budget(tmp_path / "budget.json", "different-scope", resume=True)


def test_real_mode_requires_authorization_bound_to_frozen_manifest(tmp_path):
    m = module()
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"frozen":true}', encoding="utf-8")
    with pytest.raises(ValueError):
        m.require_authorization(tmp_path)
    authorization = dict(limit=80, manifest_sha256=m.d5.d4.digest(manifest.read_bytes()))
    (tmp_path / "authorization.json").write_text(json.dumps(authorization), encoding="utf-8")
    assert m.require_authorization(tmp_path) == authorization
    manifest.write_text('{"frozen":false}', encoding="utf-8")
    with pytest.raises(ValueError):
        m.require_authorization(tmp_path)
