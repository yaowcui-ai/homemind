"""Offline import and in-memory workflow check, not a MySQL integration test."""

import json
import os
from importlib.metadata import version
from typing import TypedDict
from unittest.mock import patch


class CheckState(TypedDict):
    value: int


def check() -> dict[str, object]:
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"

    network_error = RuntimeError("Network is disabled in this check")
    with patch("socket.socket.connect", side_effect=network_error):
        from langchain_core.tools import tool
        from langgraph.checkpoint.base import BaseCheckpointSaver
        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.checkpoint.mysql.asyncmy import AsyncMySaver
        from langgraph.graph import END, START, StateGraph

        @tool
        def increment(value: int) -> int:
            """Increment a local integer without external services."""
            return value + 1

        builder = StateGraph(CheckState)
        builder.add_node("increment", lambda state: {"value": increment.invoke(state)})
        builder.add_edge(START, "increment")
        builder.add_edge("increment", END)
        graph = builder.compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "homemind-m1-offline-check"}}
        result = graph.invoke({"value": 1}, config)
        if result["value"] != 2 or graph.get_state(config).values["value"] != 2:
            raise RuntimeError("In-memory graph result or checkpoint differs from expectation")
        if not issubclass(AsyncMySaver, BaseCheckpointSaver):
            raise RuntimeError("MySQL adapter does not implement the checkpoint base class")

    packages = (
        "fastapi",
        "starlette",
        "langchain",
        "langchain-core",
        "langgraph",
        "langgraph-checkpoint",
        "langgraph-checkpoint-mysql",
        "asyncmy",
    )
    return {
        "versions": {name: version(name) for name in packages},
        "langchain_tool": "passed",
        "langgraph_memory_checkpoint": "passed",
        "mysql_adapter_import": "passed",
        "mysql_connection_and_restore": "not_run",
        "model_invocations": 0,
        "network_connections_allowed": False,
    }


if __name__ == "__main__":
    print(json.dumps(check(), ensure_ascii=False, indent=2))
