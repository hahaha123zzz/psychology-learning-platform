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


class RubricCriterion(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    points: float = Field(gt=0)
    anchors: dict[str, str] = Field(min_length=2, max_length=5)


class RubricCreate(BaseModel):
    question_version_id: str = Field(min_length=26, max_length=26)
    criteria: list[RubricCriterion] = Field(min_length=1, max_length=30)
    max_score: float = Field(gt=0)
    evidence_refs: list[str] = Field(min_length=1, max_length=30)


class RubricApproval(BaseModel):
    reason: str = Field(min_length=8, max_length=500)


class QuestionPurposeDecision(BaseModel):
    decision: str = Field(pattern="^(approved|revoked)$")
    reason: str = Field(min_length=8, max_length=500)


class AssessmentPreview(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    question_ids: list[str] = Field(min_length=1, max_length=100)
    purpose: str = Field(default="practice", pattern="^(practice|formal)$")
    result_visibility_policy: str | None = Field(
        default=None,
        pattern="^(immediate_after_submission|after_close|after_grading|manual_release)$",
    )
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    points_per_question: float = Field(default=1.0, gt=0)
    rubric_version_ids: dict[str, str] = Field(default_factory=dict)


class AssessmentResultsRelease(BaseModel):
    expected_version: int = Field(ge=1)


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
    purpose: str = Field(default="practice", pattern="^(practice|formal)$")
    result_visibility_policy: str | None = Field(
        default=None,
        pattern="^(immediate_after_submission|after_close|after_grading|manual_release)$",
    )
    rubric_version_ids: dict[str, str] = Field(default_factory=dict)


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


class AnswerFlagUpdate(BaseModel):
    answer_version: int = Field(ge=1)
    flagged: bool


class TeacherGradingItem(BaseModel):
    question_version_id: str = Field(min_length=26, max_length=26)
    points_awarded: float = Field(ge=0)
    rationale: str = Field(min_length=1, max_length=5000)


class TeacherGradeSubmit(BaseModel):
    expected_score_version: int = Field(ge=0)
    items: list[TeacherGradingItem] = Field(min_length=1)
    override_reason: str | None = Field(default=None, max_length=2000)
