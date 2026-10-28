"""S1 LangGraph: bounded goal extraction, isolated forecast, then one planning role."""

import asyncio
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from homemind.agent import graph as planner_graph
from homemind.agent.forecast import run_forecast, validate_goal
from homemind.agent.graph import PlannerCancelled, run_planner
from homemind.agent.schemas import GOAL_OUTPUT, SELECTION_OUTPUT
from homemind.agent.validation import ambiguous_question
from homemind.simulation.models import SimulationError


class PipelineState(TypedDict, total=False):
    output: dict | None
    failure_code: str | None


async def run_pipeline(model, snapshot, preferences, conversation, engine, request, used_calls):
    started = time.monotonic()
    deadline = started + planner_graph.ROUND_TIMEOUT_SECONDS
    result = dict(
        model_calls=0,
        tool_calls=0,
        usage=None,
        records=[],
        output=None,
        failure_code=None,
        actual_model=None,
        elapsed_ms=0,
        goal=None,
        forecast=None,
        selected_candidate_id=None,
        preference_optimal=None,
    )
    remaining_calls = min(6, max(0, 12 - used_calls))

    def merge(stage):
        prior_calls = result["model_calls"]
        result["model_calls"] += stage["model_calls"]
        result["tool_calls"] += stage["tool_calls"]
        result["usage"] = (
            {
                k: (result["usage"] or {}).get(k, 0) + stage["usage"][k]
                for k in ("input_tokens", "output_tokens")
            }
            if stage["usage"] is not None and (not prior_calls or result["usage"] is not None)
            else None
        )
        result["records"].extend(stage["records"])
        result["actual_model"] = stage["actual_model"]
        result["output"], result["failure_code"] = stage["output"], stage["failure_code"]

    async def invoke_stage(**kwargs):
        offset_ms = round((time.monotonic() - started) * 1000)

        def align_timing(stage):
            for record in stage["records"]:
                if "elapsed_ms" in record:
                    record["elapsed_ms"] += offset_ms
            return stage

        try:
            stage = await run_planner(
                model, snapshot, preferences, conversation, deadline=deadline, **kwargs
            )
        except PlannerCancelled as error:
            merge(align_timing(error.result))
            raise
        merge(align_timing(stage))

    async def extract(_state):
        if not remaining_calls:
            result["failure_code"] = "task_model_budget"
        else:
            await invoke_stage(
                output_adapter=GOAL_OUTPUT,
                model_budget=1,
                goal_stage=True,
                public_context={"home": snapshot, "preferences": preferences},
            )
        if not result["failure_code"] and result["output"]["kind"] == "goal":
            ambiguous = (
                ambiguous_question(snapshot, request["text"]) if len(conversation) == 1 else None
            )
            if ambiguous:
                result["output"] = ambiguous
            elif engine is None:
                result["failure_code"] = "forecast_unavailable"
                result["failure_message"] = "家庭规模超过预测上限，暂不能预测"
            else:
                result["goal"] = validate_goal(engine, result["output"], request)
        return dict(output=result["output"], failure_code=result["failure_code"])

    async def forecast(_state):
        forecast_started = time.monotonic()
        result["forecast"] = await run_forecast(engine, result["goal"], deadline)
        result["records"].append(
            {
                "stage": "forecast",
                "message": "隔离仿真预测已完成，未改变家庭状态",
                "duration_ms": round((time.monotonic() - forecast_started) * 1000),
            }
        )
        result["output"] = None
        if not any(c["deadline_met"] for c in result["forecast"]["candidates"]):
            result["output"] = dict(
                kind="clarify",
                question="本轮所有允许的方案都无法在指定期限内达到目标。请明确是否修改温度、期限或允许的风速？",
                options=[],
            )
        return dict(output=result["output"])

    async def planning(_state):
        budget = min(5, remaining_calls - result["model_calls"])
        if budget <= 0:
            result["failure_code"] = "task_model_budget"
        else:
            await invoke_stage(
                output_adapter=SELECTION_OUTPUT,
                model_budget=budget,
                public_context=dict(
                    home=snapshot,
                    preferences=preferences,
                    goal=result["goal"],
                    forecast=result["forecast"],
                ),
            )
        return dict(output=result["output"], failure_code=result["failure_code"])

    graph = StateGraph(PipelineState)
    graph.add_node("goal", extract)
    graph.add_node("forecast", forecast)
    graph.add_node("planner", planning)
    graph.add_edge(START, "goal")
    graph.add_conditional_edges(
        "goal",
        lambda state: (
            "forecast"
            if not state.get("failure_code") and state["output"]["kind"] == "goal"
            else END
        ),
    )
    graph.add_conditional_edges("forecast", lambda state: END if state.get("output") else "planner")
    graph.add_edge("planner", END)
    try:
        with tracing_context(enabled=False):
            await graph.compile().ainvoke({})
    except SimulationError as error:
        result["output"] = None
        result["failure_code"], result["failure_message"] = error.code, error.message
    except TimeoutError:
        result["failure_code"] = "round_timeout"
    except Exception:
        result["output"] = None
        result["failure_code"] = "forecast_unavailable"
        result["failure_message"] = "预测计算暂不可用，本轮未发送设备动作，请稍后重试"
    except asyncio.CancelledError:
        result["output"] = None
        result["failure_code"] = "request_cancelled"
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        raise PlannerCancelled(result) from None
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return result
