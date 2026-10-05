from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ActivityType = Literal["reteach", "practice_set", "mini_lab", "discussion", "review"]
InterventionStatus = Literal["draft", "scheduled", "active", "completed", "evaluated", "archived"]


class InterventionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    activity_type: ActivityType
    class_id: str | None = Field(default=None, min_length=26, max_length=26)
    target_snapshot: dict[str, Any] = Field(min_length=1)
    plan: dict[str, Any] = Field(min_length=1)


class InterventionTransition(BaseModel):
    version: int = Field(ge=1)


class InterventionSchedule(InterventionTransition):
    scheduled_at: datetime


class InterventionEvaluate(BaseModel):
    version: int = Field(ge=1)
    outcome: dict[str, Any] = Field(min_length=1)


class InterventionDispatch(BaseModel):
    version: int = Field(ge=1)
    user_ids: list[str] = Field(min_length=1, max_length=200)


class InterventionRunComplete(BaseModel):
    version: int = Field(ge=1)
    outcome: dict[str, Any] = Field(default_factory=dict)


class InterventionOut(BaseModel):
    id: str
    course_id: str
    class_id: str | None
    created_by: str
    approved_by: str | None
    title: str
    activity_type: ActivityType
    target_snapshot: dict[str, Any]
    plan: dict[str, Any]
    status: InterventionStatus
    scheduled_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    evaluated_at: datetime | None
    outcome: dict[str, Any] | None
    version: int
    created_at: datetime
    updated_at: datetime


class InterventionRunOut(BaseModel):
    id: str
    intervention_id: str
    course_id: str
    user_id: str
    status: Literal["scheduled", "in_progress", "paused", "completed", "cancelled"]
    started_at: datetime | None
    completed_at: datetime | None
    outcome: dict[str, Any] | None
    version: int
    created_at: datetime
    updated_at: datetime


ObservationType = Literal["misconception", "strategy", "support_need", "progress"]
ObservationQualification = Literal["pending", "qualified", "rejected"]
ObservationReviewDecision = Literal["pending", "accepted", "rejected"]


class TeacherObservationCreate(BaseModel):
    student_id: str = Field(min_length=26, max_length=26)
    class_id: str = Field(min_length=26, max_length=26)
    observation_type: ObservationType
    note: str = Field(min_length=1, max_length=2000)
    evidence_refs: list[str] = Field(min_length=1, max_length=20)

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, references: list[str]) -> list[str]:
        if any(len(reference) != 26 for reference in references):
            raise ValueError("evidence_refs must contain LearningEvidence IDs")
        return references


class TeacherObservationReview(BaseModel):
    version: int = Field(ge=1)
    decision: Literal["qualified", "rejected"]
    reason: str = Field(min_length=1, max_length=500)


class TeacherObservationRevalidation(BaseModel):
    version: int = Field(ge=1)
    learning_event_id: str = Field(min_length=26, max_length=26)


class TeacherObservationRevalidationCandidate(BaseModel):
    learning_event_id: str
    qualification_id: str
    event_type: str
    source_type: str
    occurred_at: datetime
    qualified_at: datetime
    evidence_count: int
    evidence_ids: list[str]


class TeacherObservationOut(BaseModel):
    id: str
    course_id: str
    class_id: str | None
    student_id: str
    teacher_id: str
    observation_type: ObservationType
    note: str
    evidence_refs: list[str]
    qualification_status: ObservationQualification
    review_decision: ObservationReviewDecision = "pending"
    verification_status: Literal["pending", "qualified", "rejected", "invalidated"]
    verification_event_id: str | None
    verification_qualification_id: str | None
    verification_evidence_ids: list[str]
    verification_algorithm_version: str | None
    verification_reason: str | None
    verified_at: datetime | None
    source_evidence_status: Literal["valid", "invalidated", "unavailable"] = "unavailable"
    algorithm_version: str | None
    reviewed_by: str | None
    review_reason: str | None
    reviewed_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
