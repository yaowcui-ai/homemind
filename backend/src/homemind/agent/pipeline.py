"""Shared goal/forecast graph with S1 planning or parallel read-only experts."""

import asyncio
import time
from copy import deepcopy
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from homemind.agent import graph as planner_graph
from homemind.agent.budget import CallBudget
from homemind.agent.diagnostics import failure_record
from homemind.agent.experts import ROLES, advice_failure, skipped_role
from homemind.agent.forecast import run_forecast, validate_goal
from homemind.agent.graph import PlannerCancelled, run_planner
from homemind.agent.schemas import ADVICE_OUTPUT, GOAL_OUTPUT, SELECTION_OUTPUT
from homemind.agent.validation import ambiguous_question
from homemind.simulation.models import SimulationError


class PipelineState(TypedDict, total=False):
    output: dict | None
    failure_code: str | None
    comfort_done: bool
    energy_done: bool


async def run_pipeline(model, snapshot, preferences, conversation, engine, request, used_calls):
    started = time.monotonic()
    deadline = started + planner_graph.ROUND_TIMEOUT_SECONDS
    expert_mode = request.get("strategy") == "expert_forecast"
    budget = CallBudget(used_calls)
    roles = {role: skipped_role(role) for role in ROLES}
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
    if expert_mode:
        result["role_runs"] = list(roles.values())

    def merge(stage):
        prior_calls = result["model_calls"]
        result["model_calls"] += stage["model_calls"]
        result["tool_calls"] += stage["tool_calls"]
        if stage["model_calls"]:
            result["usage"] = (
                {
                    key: (result["usage"] or {}).get(key, 0) + stage["usage"][key]
                    for key in ("input_tokens", "output_tokens")
                }
                if stage["usage"] is not None and (not prior_calls or result["usage"] is not None)
                else None
            )
            result["actual_model"] = stage["actual_model"]
        result["records"].extend(stage["records"])

    async def invoke_stage(role, **kwargs):
        offset_ms = round((time.monotonic() - started) * 1000)
        cancelled = False
        try:
            stage = await run_planner(
                model,
                snapshot,
                preferences,
                conversation,
                deadline=deadline,
                reserve_call=budget.reserve,
                **kwargs,
            )
        except PlannerCancelled as error:
            stage, cancelled = error.result, True
        if role in {"comfort", "energy"} and not stage["failure_code"]:
            diagnostic = advice_failure(stage["output"], role, result["forecast"])
            if diagnostic is not None:
                stage["records"].append(failure_record(role, *diagnostic))
                stage["output"] = None
                stage["failure_code"] = "invalid_advice"
        for record in stage["records"]:
            if "elapsed_ms" in record:
                record["elapsed_ms"] += offset_ms
        merge(stage)
        if expert_mode:
            ledger = roles[role]
            ledger.update(
                status="cancelled"
                if cancelled
                else "failed"
                if stage["failure_code"]
                else "succeeded",
                **{
                    key: stage[key]
                    for key in (
                        "model_calls",
                        "tool_calls",
                        "usage",
                        "actual_model",
                        "elapsed_ms",
                        "failure_code",
                    )
                },
                advice=stage["output"]
                if role in {"comfort", "energy"} and not stage["failure_code"]
                else None,
            )
        if cancelled:
            raise asyncio.CancelledError
        return stage

    async def extract(_state):
        if not budget.remaining:
            result["failure_code"] = "task_model_budget"
        else:
            stage = await invoke_stage(
                "coordinator_goal",
                output_adapter=GOAL_OUTPUT,
                model_budget=1,
                goal_stage=True,
                public_context={"home": snapshot, "preferences": preferences},
            )
            result["output"], result["failure_code"] = stage["output"], stage["failure_code"]
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
            dict(
                stage="forecast",
                message="隔离仿真预测已完成，未改变家庭状态",
                duration_ms=round((time.monotonic() - forecast_started) * 1000),
            )
        )
        result["output"] = None
        if not any(candidate["deadline_met"] for candidate in result["forecast"]["candidates"]):
            result["output"] = dict(
                kind="clarify",
                question="本轮所有允许的方案都无法在指定期限内达到目标。请明确是否修改温度、期限或允许的风速？",
                options=[],
            )
        return dict(output=result["output"])

    def facts():
        return dict(
            home=snapshot, preferences=preferences, goal=result["goal"], forecast=result["forecast"]
        )

    async def expert(role):
        # Each branch owns its context, messages and result slot. Neither sees peer Advice.
        criterion = (
            "minimize (first_observed_goal_minute, energy_wh)"
            if role == "comfort"
            else "minimize (energy_wh, first_observed_goal_minute)"
        )
        await invoke_stage(
            role,
            output_adapter=ADVICE_OUTPUT,
            model_budget=1,
            allow_tools=False,
            public_context=deepcopy(facts() | {"role": role}),
            role_instructions=(
                f"You are HomeMind's {role} expert. Return Advice in ONE read-only request. "
                "Inspect original conversation, public home/preferences, GoalContract and ALL "
                "forecast candidates. Never call tools or change targets, deadlines, scope or "
                "fan constraints. "
                "If original text conflicts with the goal, clarify. Refuse unsupported requests. "
                "Recommend deadline_met candidates. Evidence is goal or candidate:<actual id>; "
                "recommendations must cite their candidate. Clarify/refuse require null candidate. "
                f"Your specialist criterion is {criterion} among ALL deadline_met candidates. "
                "The coordinator resolves tradeoffs using the user's priority. "
                "Provide at most two short public sentences citing forecast numbers, "
                "never private reasoning."
            ),
        )
        return {role + "_done": True}

    async def aggregate(_state):
        if any(roles[role]["status"] != "succeeded" for role in ("comfort", "energy")):
            result["output"], result["failure_code"] = None, "analysis_incomplete"
        else:
            # Stable order defines presentation/stop precedence, never a substitute selection.
            opinions = [roles[role]["advice"] for role in ("comfort", "energy")]
            refusal = next((a for a in opinions if a["outcome"] == "refuse"), None)
            clarification = next((a for a in opinions if a["outcome"] == "clarify"), None)
            if refusal:
                result["output"] = dict(kind="refuse", reason=refusal["public_summary"])
            elif clarification:
                result["output"] = dict(
                    kind="clarify", question=clarification["public_summary"], options=[]
                )
        return dict(output=result["output"], failure_code=result["failure_code"])

    async def planning(_state):
        stage_budget = min(3 if expert_mode else 5, budget.remaining)
        if not stage_budget:
            result["failure_code"] = "task_model_budget"
            return dict(output=None, failure_code=result["failure_code"])
        context = facts()
        if expert_mode:
            context |= dict(
                role="coordinator", advice=[roles[role]["advice"] for role in ("comfort", "energy")]
            )
        stage = await invoke_stage(
            "coordinator_plan",
            output_adapter=SELECTION_OUTPUT,
            model_budget=stage_budget,
            allow_tools=False,
            public_context=context,
        )
        result["output"], result["failure_code"] = stage["output"], stage["failure_code"]
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
    if expert_mode:

        async def comfort(state):
            return await expert("comfort")

        async def energy(state):
            return await expert("energy")

        graph.add_node("comfort", comfort)
        graph.add_node("energy", energy)
        graph.add_node("aggregate", aggregate)
        graph.add_conditional_edges(
            "forecast", lambda state: END if state.get("output") else ["comfort", "energy"]
        )
        graph.add_edge(["comfort", "energy"], "aggregate")
        graph.add_conditional_edges(
            "aggregate",
            lambda state: END if state.get("output") or state.get("failure_code") else "planner",
        )
    else:
        graph.add_conditional_edges(
            "forecast", lambda state: END if state.get("output") else "planner"
        )
    graph.add_edge("planner", END)
    execution = None
    try:
        with tracing_context(enabled=False):
            execution = asyncio.create_task(graph.compile().ainvoke({}))
            await asyncio.shield(execution)
    except asyncio.CancelledError:
        if execution is not None:
            execution.cancel()
            # Wait until every parallel node has settled its actual issued accounting.
            await asyncio.gather(execution, return_exceptions=True)
        result["output"], result["failure_code"] = None, "request_cancelled"
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        raise PlannerCancelled(result) from None
    except SimulationError as error:
        result["output"] = None
        result["failure_code"], result["failure_message"] = error.code, error.message
    except TimeoutError:
        result["failure_code"] = "round_timeout"
    except Exception:
        result["output"], result["failure_code"] = None, "forecast_unavailable"
        result["failure_message"] = "预测计算暂不可用，本轮未发送设备动作，请稍后重试"
    result["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return result
