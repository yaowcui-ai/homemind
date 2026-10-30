"""Public fact projections must preserve ownership, precision and original ordering."""

import asyncio
import json
from copy import deepcopy
from decimal import Decimal

from langchain_core.messages import AIMessage

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


def test_goal_history_uses_user_requests_without_promoting_assistant_restatement():
    from homemind.agent.graph import run_planner
    from homemind.agent.schemas import GOAL_OUTPUT
    from homemind.simulation.service import SimulationService

    original = "100分钟内降温，优先尽快达标，然后省电，目标温度稍后告诉你。"
    polluted = "请提供温度，我会按省电优先规划。"
    reply = "25度，其余不变。"
    conversation = [
        dict(role="user", text=original),
        dict(role="assistant", text=polluted),
        dict(role="user", text=reply),
    ]

    class InspectModel:
        async def ainvoke(self, messages, tools):
            facts, _ = json.JSONDecoder().raw_decode(
                messages[0].content.split("Frozen public context: ", 1)[1]
            )
            assert facts["user_request_history"] == [original, reply]
            assert len(messages) == 4  # Preserve full conversation for the question context.
            return AIMessage(
                content=json.dumps(dict(kind="clarify", question="受控检查", options=[]))
            )

    snapshot = SimulationService().snapshot()
    result = asyncio.run(
        run_planner(
            InspectModel(),
            snapshot,
            {},
            conversation,
            output_adapter=GOAL_OUTPUT,
            goal_stage=True,
            public_context={"home": snapshot},
            model_budget=1,
        )
    )
    assert result["failure_code"] is None


def test_provider_http_failure_keeps_status_without_response_body_or_key(monkeypatch):
    import httpx
    from pydantic import SecretStr

    from homemind.agent.model import DeepSeekModel, ModelFailure
    from homemind.config import Settings

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(503, json={"error": "PRIVATE-DO-NOT-LOG"})
    )
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs)
    )
    model = DeepSeekModel(Settings(_env_file=None, model_api_key=SecretStr("synthetic-unit-key")))
    try:
        asyncio.run(model.ainvoke([], []))
    except ModelFailure as error:
        assert error.http_status == 503
        assert str(error) == "model_unavailable"
        assert "PRIVATE" not in repr(error) and "synthetic-unit-key" not in repr(error)
    else:
        raise AssertionError("Provider failure must fail closed")
