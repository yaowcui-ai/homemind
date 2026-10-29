"""Oracle corrections remain separate from immutable original runs."""

import importlib.util
import sys
from pathlib import Path


def module():
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "product_d4_audit", root / "evaluation/probes/product_d4_audit.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_keep_cover_list_is_redundant_when_cover_constraint_freezes_it():
    m = module()
    goal = dict(cover_constraint="keep", cover_entity_id="cover", keep_entity_ids=["lamp", "cover"])
    assert m.canonical_goal(goal)["keep_entity_ids"] == ["lamp"]
    assert goal["keep_entity_ids"] == ["lamp", "cover"]


def test_free_text_exception_needs_explicit_hash_bound_review():
    m = module()
    record = dict(
        case_id="DD06",
        final_task=dict(
            status="waiting_input",
            actions=[],
            agent_run=dict(question="请先恢复客厅窗户读数", options=[]),
        ),
        gold={},
        oracle_forecast=None,
        initial_snapshot={"entities": []},
        final_snapshot={"entities": []},
        score={"confirmation_observed": False},
    )
    assert not m.audit_score(record)["case_pass"]
    assert not m.audit_score(record, dict(correct=True, question_sha256="wrong"))["case_pass"]
    review = dict(
        correct=True,
        question_sha256=m.d4.digest("请先恢复客厅窗户读数".encode()),
        reviewer="development_assistant",
        reason="明确恢复窗户读数；只评首轮",
    )
    assert m.audit_score(record, review)["case_pass"]
