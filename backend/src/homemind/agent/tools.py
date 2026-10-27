"""The only model tools expose copies of a frozen public snapshot."""

from copy import deepcopy

from langchain_core.tools import StructuredTool
from langchain_core.utils.function_calling import convert_to_openai_tool

from homemind.simulation.models import InputModel


class EmptyArguments(InputModel):
    pass


def frozen_tools(snapshot, preferences):
    home_copy, preferences_copy = deepcopy(snapshot), deepcopy(preferences)

    def read_home():
        return deepcopy(home_copy)

    def read_preferences():
        return deepcopy(preferences_copy)

    result = {
        name: StructuredTool.from_function(
            func=func, name=name, description=description, args_schema=EmptyArguments
        )
        for name, func, description in [
            ("read_home", read_home, "Read this task's frozen public household facts."),
            (
                "read_preferences",
                read_preferences,
                "Read this task's frozen household preferences.",
            ),
        ]
    }
    return result, [convert_to_openai_tool(tool) for tool in result.values()]
