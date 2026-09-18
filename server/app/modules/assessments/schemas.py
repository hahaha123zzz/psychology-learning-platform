from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class QuestionOption(BaseModel):
    key: str = Field(min_length=1, max_length=8)
    text: str = Field(min_length=1, max_length=1000)
    is_correct: bool = False


class QuestionCreate(BaseModel):
    type: str = Field(pattern="^(single|multiple|true_false|short_answer|essay)$")
    stem: str = Field(min_length=1, max_length=5000)
    options: list[QuestionOption] | None = None
    answer: dict[str, Any] | None = None
    rubric: str | None = Field(default=None, max_length=5000)
    explanation: str | None = Field(default=None, max_length=5000)
    difficulty: int = Field(ge=1, le=5)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class QuestionReview(BaseModel):
    action: str = Field(pattern="^(approve|reject|request_changes)$")
    version: int = Field(ge=1)
    comment: str | None = Field(default=None, max_length=2000)


class AssessmentCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    question_ids: list[str] = Field(min_length=1)
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    ai_policy: str = Field(
        default="full_after_submit",
        pattern="^(disabled|direction_only|full_after_submit)$",
    )
    points_per_question: float = Field(default=1.0, gt=0)


class AssessmentItemOut(BaseModel):
    question_version_id: str
    order_no: int
    points: float
    type: str
    stem: str
    options: list | None


class AnswerSave(BaseModel):
    answer_version: int = Field(ge=1)
    response: dict[str, Any] | None = None
    client_saved_at: datetime | None = None
