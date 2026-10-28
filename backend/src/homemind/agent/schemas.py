"""Strict public request and planner contracts."""

from typing import Annotated, Literal

from pydantic import Field, StrictInt, TypeAdapter, model_validator

from homemind.simulation.models import Identifier, InputModel, Minutes, TargetTemperature

Text = Annotated[str, Field(strict=True, min_length=1, max_length=2000)]


class AgentRequest(InputModel):
    text: Text
    expected_world_id: Identifier
    keep_entity_ids: list[Identifier] = Field(default_factory=list, max_length=1000)
    protected_room_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    strategy: Literal["standard", "single_forecast"] = "standard"


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


class GoalContract(InputModel):
    nullable_fields = frozenset({"cover_entity_id"})
    kind: Literal["goal"]
    room_id: Identifier
    climate_entity_id: Identifier
    cover_entity_id: Identifier | None
    target_temperature_c: TargetTemperature
    ready_in_minutes: Minutes
    priority: Literal["comfort_first", "energy_first"]
    allowed_fan_modes: list[Literal["low", "auto"]] = Field(min_length=1, max_length=2)
    cover_constraint: Literal["allow_open_close", "keep"]
    keep_entity_ids: list[Identifier] = Field(max_length=1000)
    protected_room_ids: list[Identifier] = Field(max_length=100)

    @model_validator(mode="after")
    def unique_references(self):
        for values in (self.allowed_fan_modes, self.keep_entity_ids, self.protected_room_ids):
            if len(set(values)) != len(values):
                raise ValueError("重复引用")
        return self


class Selection(InputModel):
    kind: Literal["selection"]
    candidate_id: Annotated[str, Field(strict=True, min_length=1, max_length=80)]
    plan: Plan


GOAL_OUTPUT = TypeAdapter(Annotated[GoalContract | Clarify | Refuse, Field(discriminator="kind")])
SELECTION_OUTPUT = TypeAdapter(Annotated[Selection | Clarify | Refuse, Field(discriminator="kind")])
