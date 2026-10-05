from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MiniLabPhase = Literal["intro", "predict", "run", "inspect", "explain", "summary"]


class MiniLabChoiceStage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=500)
    choices: list[str] = Field(min_length=2, max_length=8)

    @field_validator("prompt")
    @classmethod
    def prompt_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("实验提示不能为空")
        return value

    @field_validator("choices")
    @classmethod
    def choices_are_safe_and_distinct(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value or len(value) > 240 for value in normalized):
            raise ValueError("实验选项必须是非空短文本")
        if len(set(normalized)) != len(normalized):
            raise ValueError("实验选项不能重复")
        return values


class MiniLabDefinition(BaseModel):
    """Mini Lab 的通用、纯文本定义合同；实验动作由固定运行时实现。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    title: str = Field(min_length=1, max_length=160)
    intro: str = Field(min_length=1, max_length=1200)
    prediction: MiniLabChoiceStage
    run: MiniLabChoiceStage
    inspect: str = Field(min_length=1, max_length=1200)
    explanation: str = Field(min_length=1, max_length=1200)
    summary: str = Field(min_length=1, max_length=1200)
    knowledge_point: str | None = Field(default=None, max_length=240)
    source_status: Literal["engineering_fixture"]
    source_note: str = Field(min_length=1, max_length=500)

    @field_validator("title", "intro", "inspect", "explanation", "summary", "source_note")
    @classmethod
    def text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("实验定义文本不能为空")
        return value


class MiniLabCreate(BaseModel):
    course_id: str = Field(min_length=26, max_length=26)
    lab_key: str = Field(min_length=1, max_length=80)


class MiniLabTrial(BaseModel):
    phase: MiniLabPhase
    response: int | None = Field(default=None, ge=0, le=20)
    rt: int | None = Field(default=None, ge=0, le=3_600_000)
    recorded_at: str = Field(min_length=1, max_length=80)


class MiniLabResult(BaseModel):
    version: int = Field(ge=1)
    schema_version: Literal["mini-lab.v1"]
    definition_id: str = Field(min_length=1, max_length=80)
    runtime: Literal["jspsych"]
    trial_data: list[MiniLabTrial] = Field(min_length=6, max_length=6)
    completed_at: str = Field(min_length=1, max_length=80)


class MiniLabProgress(BaseModel):
    version: int = Field(ge=1)
    trial_data: list[MiniLabTrial] = Field(min_length=1, max_length=6)


class MiniLabInvalidate(BaseModel):
    expected_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("idempotency_key", "reason")
    @classmethod
    def values_are_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("作废幂等键和理由不能为空")
        return value.strip()


class MiniLabOut(BaseModel):
    id: str
    course_id: str
    lab_key: str
    definition_snapshot: dict[str, Any]
    status: str
    phase: str
    trial_data: list[dict[str, Any]]
    derived_measure: dict[str, Any] | None
    version: int
    started_at: str
    completed_at: str | None
    invalidation_reason: str | None
    invalidated_at: str | None
    created_at: str
    updated_at: str


class MiniLabResponseMeta(BaseModel):
    request_id: str | None
    server_time: str


class MiniLabResponse(BaseModel):
    data: MiniLabOut
    meta: MiniLabResponseMeta
