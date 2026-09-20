from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlayerContext(StrictModel):
    selected_abilities: list[int] = Field(default_factory=list, max_length=6)
    slot: int = Field(default=1, ge=1, le=8)
    team_number: int = Field(default=1, ge=1, le=8)


class OpponentContext(StrictModel):
    known_abilities: list[int] = Field(default_factory=list, max_length=9)
    observations: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    slot: int = Field(default=2, ge=1, le=8)
    team_number: int = Field(default=2, ge=1, le=8)


class MatchContext(StrictModel):
    schema_version: Literal["bot-fight-ai-match-context-v1"]
    ruleset_version: Literal["duel-v1"]
    brain_schema_version: Literal["bot-logic-tree-v1"]
    match_id: str = Field(min_length=1, max_length=200)
    round_number: int = Field(ge=0)
    seed: int
    self: PlayerContext
    opponent: OpponentContext
    previous_round_telemetry: list[dict[str, Any]] = Field(default_factory=list, max_length=10)


class DecisionPlayerContext(StrictModel):
    selected_abilities: list[int] = Field(default_factory=list, max_length=6)
    known_opponent_abilities: list[int] = Field(default_factory=list, max_length=9)
    slot: int = Field(ge=1, le=8)
    team_number: int = Field(ge=1, le=8)
    opponent_slot: int = Field(ge=1, le=8)
    opponent_team_number: int = Field(ge=1, le=8)


class DecisionRequest(StrictModel):
    schema_version: Literal["bot-fight-ai-match-context-v1"] = "bot-fight-ai-match-context-v1"
    ruleset_version: Literal["duel-v1"]
    brain_schema_version: Literal["bot-logic-tree-v1"]
    match_id: str = Field(min_length=1, max_length=200)
    round_number: int = Field(ge=1, le=3)
    seed: int
    candidate_count: int = Field(ge=1, le=20)
    player_a: DecisionPlayerContext
    player_b: DecisionPlayerContext
    previous_round_telemetry: list[dict[str, Any]] = Field(default_factory=list, max_length=10)


class GenerateRequest(StrictModel):
    context: MatchContext
    candidate_count: int = Field(default=10, ge=1, le=20)
    instructions: str | None = Field(default=None, max_length=8000)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class ValidationIssue(StrictModel):
    code: str
    path: str
    message: str


class CandidateValidation(StrictModel):
    candidate_id: str | None
    valid: bool
    issues: list[ValidationIssue]


class GenerateResponse(StrictModel):
    model: str
    prompt_version: str
    candidate_count: int
    raw_response: str
    parsed_response: Any | None
    parse_error: str | None
    candidate_validation: list[CandidateValidation]
    ollama_metadata: dict[str, Any]


class ValidateBrainRequest(StrictModel):
    brain: dict[str, Any]


class SimulationRequest(StrictModel):
    scenario_id: str = Field(min_length=1, max_length=200)
    seed: int
    candidate_brain: dict[str, Any]
    opponent_brain: dict[str, Any]


class EvaluationProgram(StrictModel):
    program_id: str = Field(min_length=1, max_length=200)
    brain: dict[str, Any]


class EvaluationRequest(StrictModel):
    candidates: list[EvaluationProgram] = Field(min_length=1, max_length=20)
    opponents: list[EvaluationProgram] = Field(min_length=1, max_length=10)
    seeds: list[int] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def bounded_scenario_count(self) -> "EvaluationRequest":
        candidate_ids = [value.program_id for value in self.candidates]
        opponent_ids = [value.program_id for value in self.opponents]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("candidate program_id values must be unique")
        if len(set(opponent_ids)) != len(opponent_ids):
            raise ValueError("opponent program_id values must be unique")
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("evaluation seeds must be unique")
        if len(self.candidates) * len(self.opponents) * len(self.seeds) > 200:
            raise ValueError("candidate × opponent × seed scenarios cannot exceed 200")
        return self
