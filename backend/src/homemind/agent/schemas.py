"""Strict public request and planner contracts."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, TypeAdapter

from homemind.simulation.models import Identifier, InputModel, Minutes, TargetTemperature

Text = Annotated[str, Field(strict=True, min_length=1, max_length=2000)]


class AgentRequest(InputModel):
    text: Text
    expected_world_id: Identifier
    keep_entity_ids: list[Identifier] = Field(default_factory=list, max_length=1000)
    protected_room_ids: list[Identifier] = Field(default_factory=list, max_length=100)


class ReplyRequest(InputModel):
    text: Text
    expected_turn: Annotated[StrictInt, Field(ge=0, le=3)]


class ConfirmRequest(InputModel):
    expected_turn: Annotated[StrictInt, Field(ge=0, le=3)]


class Option(InputModel):
    id: Identifier
    label: Annotated[str, Field(strict=True, min_length=1, max_length=80)]
    kind: Literal["room", "entity"]


class Clarify(InputModel):
    kind: Literal["clarify"]
    question: Text
    options: list[Option] = Field(max_length=100)


class Refuse(InputModel):
    kind: Literal["refuse"]
    reason: Text


class Intent(InputModel):
    entity_id: Identifier
    room_id: Identifier
    action: Literal["set_light", "set_climate", "set_cover"]
    parameters: dict


class TemperatureGoal(InputModel):
    room_id: Identifier
    target: TargetTemperature


class Plan(InputModel):
    nullable_fields = frozenset({"ready_in_minutes"})
    kind: Literal["plan"]
    scenario: Literal["homecoming", "sleep", "away", "local"]
    room_ids: list[Identifier] = Field(min_length=1, max_length=100)
    keep_entity_ids: list[Identifier] = Field(max_length=1000)
    protected_room_ids: list[Identifier] = Field(max_length=100)
    actions: list[Intent] = Field(min_length=1, max_length=100)
    temperatures: list[TemperatureGoal] = Field(max_length=100)
    ready_in_minutes: Minutes | None
    rationale: Text


OUTPUT = TypeAdapter(Annotated[Plan | Clarify | Refuse, Field(discriminator="kind")])
