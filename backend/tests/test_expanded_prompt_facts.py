"""Public fact projections must preserve ownership, precision and original ordering."""

from copy import deepcopy
from decimal import Decimal

from homemind.agent.prompts import prepare_context


def test_room_index_never_binds_a_protected_rooms_light_to_target_room():
    context = {
        "home": {
            "rooms": [{"id": "target", "name": "排练房"}, {"id": "protected", "name": "客厅"}],
            "entities": [
                {"id": "other-light", "name": "客厅灯", "room_id": "protected", "type": "light"},
                {"id": "target-light", "name": "排练房灯", "room_id": "target", "type": "light"},
            ],
        }
    }
    before = deepcopy(context)
    actual = prepare_context(context, goal_stage=True)
    assert actual["room_entity_index"]["target"]["light"] == ["target-light"]
    assert actual["room_entity_index"]["protected"]["light"] == ["other-light"]
    assert actual["home"]["entities"] == context["home"]["entities"]
    assert context == before


def test_comparison_rows_preserve_close_energy_values_and_do_not_choose_a_winner():
    context = {
        "goal": {"priority": "energy_first"},
        "forecast": {
            "candidates": [
                {
                    "id": "earlier",
                    "deadline_met": True,
                    "energy_wh": 1275.05,
                    "first_observed_goal_minute": 35,
                },
                {
                    "id": "lower-energy",
                    "deadline_met": True,
                    "energy_wh": 1275.0,
                    "first_observed_goal_minute": 38,
                },
                {
                    "id": "infeasible",
                    "deadline_met": False,
                    "energy_wh": 825,
                    "first_observed_goal_minute": None,
                },
            ]
        },
    }
    before = deepcopy(context)
    actual = prepare_context(context)
    rows = actual["candidate_comparison"]
    assert [r["id"] for r in rows] == ["earlier", "lower-energy", "infeasible"]
    assert Decimal(rows[0]["energy_wh_exact"]) - Decimal(rows[1]["energy_wh_exact"]) == Decimal(
        "0.05"
    )
    assert rows[2]["first_observed_goal_minute"] is None
    assert actual["selection_objective"] == ["energy_wh", "first_observed_goal_minute"]
    assert all(
        set(row) == {"id", "deadline_met", "energy_wh_exact", "first_observed_goal_minute"}
        for row in rows
    )
    assert context == before


def test_specialist_objective_is_role_specific_without_rewriting_user_priority():
    context = {
        "role": "comfort",
        "goal": {"priority": "energy_first"},
        "forecast": {"candidates": []},
    }
    actual = prepare_context(context)
    assert actual["selection_objective"] == ["first_observed_goal_minute", "energy_wh"]
    assert actual["goal"]["priority"] == "energy_first"
    assert actual["allowed_evidence_refs"] == ["goal"]
