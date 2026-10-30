"""Published claims must reconcile with all recorded runs, including failures."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_catalog_distinguishes_case_inventory_from_measured_runs():
    catalog = read("evaluation/case-catalog.json")
    base = {
        c["id"]
        for path in ("product-c-cases.json", "product-c2-cases.json")
        for c in read("evaluation/" + path)
    }
    expanded = read("evaluation/product-expanded-cases.json")
    final = read("evaluation/product-final-validation-cases.json")
    assert len(base) == 44
    assert len({c["id"] for c in expanded + final}) == 48
    assert len(base | {c["id"] for c in expanded + final}) == 92
    assert catalog["counts"]["development_total"] == 68
    assert catalog["counts"]["validation_total"] == 24


def test_every_published_run_and_request_reconciles_without_dropping_failures():
    summary = read("evaluation/results/product-expanded-20261030.json")
    rows = read("evaluation/results/product-expanded-public-evidence-20261030.json")["runs"]
    assert len(rows) == len({r["run_id"] for r in rows}) == summary["total_runs"] == 148
    assert sum(r["issued_requests"] for r in rows) == summary["real_requests"] == 360
    requests = [r for ledger in summary["ledgers"].values() for r in ledger["requests"]]
    assert len(requests) == 360
    assert sum("usage" not in r for r in requests) == 22
    for name, group in summary["groups"].items():
        selected = [r for r in rows if r["phase"] + "/" + r["strategy"] == name]
        assert len(selected) == group["runs"]
        assert sum(r["score"]["case_pass"] for r in selected) == group["passed"]
        assert sum(r["issued_requests"] for r in selected) == group["issued_requests"]
        for r in selected:
            assert sum(q["case_id"] == r["run_id"] for q in requests) == r["issued_requests"]
            assert len(r["source_record_sha256"]) == 64
    assert summary["groups"]["holdout/single_forecast"]["passed"] == 2
    assert summary["groups"]["holdout/expert_forecast"]["passed"] == 3
    assert summary["groups"]["candidate/single_forecast"]["passed"] == 21
    assert summary["groups"]["candidate/expert_forecast"]["passed"] == 23


def test_comparison_shares_exact_initial_facts_and_contains_no_account_material():
    evidence = read("evaluation/results/product-expanded-public-evidence-20261030.json")
    rows = evidence["runs"]
    for case in {r["case_id"] for r in rows}:
        initial = [r["initial_snapshot"] for r in rows if r["case_id"] == case]
        assert all(item == initial[0] for item in initial), case
    forbidden = {"username", "password", "csrf_token", "cookies", "api_key", "database_url"}

    def walk(value):
        if isinstance(value, dict):
            assert not (set(value) & forbidden)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            assert "C:\\Users\\" not in value and "C:/Users/" not in value

    walk(evidence)
