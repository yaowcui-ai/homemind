"""D4 ranking contract; real adherence is evaluated separately, not by this stub."""

import asyncio

from langchain_core.messages import AIMessage

from homemind.agent.graph import run_planner
from homemind.agent.schemas import SELECTION_OUTPUT


def test_both_forecast_strategies_receive_same_explicit_numeric_ranking():
    class Capture:
        prompt = ""

        async def ainvoke(self, messages, tools):
            self.prompt = messages[0].content
            return AIMessage(content='{"kind":"refuse","reason":"受控测试，无设备动作"}')

    for extra in ({}, {"role": "coordinator", "advice": []}):
        model = Capture()
        asyncio.run(
            run_planner(
                model,
                {},
                {},
                [],
                output_adapter=SELECTION_OUTPUT,
                public_context={"goal": {}, "forecast": {}, **extra},
            )
        )
        assert "energy_first: minimize (energy_wh, first_observed_goal_minute)" in model.prompt
        assert "comfort_first: minimize (first_observed_goal_minute, energy_wh)" in model.prompt
        assert "do not round away differences" in model.prompt
