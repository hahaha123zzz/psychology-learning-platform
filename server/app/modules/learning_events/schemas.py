from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class LearningEventCreate(BaseModel):
    event_key: str = Field(min_length=1, max_length=128)
    course_id: str = Field(min_length=26, max_length=26)
    event_type: str = Field(
        pattern="^(task_viewed|answer_submitted|tutor_responded|lab_trial_completed|feedback_submitted)$"
    )
    source_type: str = Field(pattern="^(tutor|assessment|practice|review|lab|system)$")
    source_ref: str | None = Field(default=None, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime | None = None


class LearningEventOut(BaseModel):
    id: str
    event_key: str
    user_id: str
    course_id: str
    event_type: str
    source_type: str
    source_ref: str | None
    payload: dict[str, Any]
    occurred_at: datetime
    qualification_status: str
    qualification_reason: str | None
    qualified_at: datetime | None
