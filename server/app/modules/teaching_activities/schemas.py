from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TeachingActivityCreate(BaseModel):
    activity_key: str = Field(
        min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    )
    title: str = Field(min_length=1, max_length=200)
    activity_type: str = Field(min_length=1, max_length=40)
    manifest: dict[str, Any] = Field(min_length=1)


class TeachingActivityUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    activity_type: str | None = Field(default=None, min_length=1, max_length=40)
    manifest: dict[str, Any] | None = Field(default=None, min_length=1)
    status: Literal["draft", "ready"] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "TeachingActivityUpdate":
        if all(
            value is None for value in (self.title, self.activity_type, self.manifest, self.status)
        ):
            raise ValueError("至少提供一个需要更新的字段")
        return self


class TeachingActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    activity_key: str
    version_no: int
    title: str
    activity_type: str
    manifest: dict[str, Any]
    status: str
    created_by: str
    published_by: str | None
    published_at: datetime | None
    supersedes_id: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class TeachingActivityRunCreate(BaseModel):
    activity_version_id: str = Field(min_length=26, max_length=26)
    scheduled_at: datetime
    target_user_ids: list[str] | None = Field(default=None, max_length=500)

    @field_validator("scheduled_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled_at 必须包含时区")
        return value

    @field_validator("target_user_ids")
    @classmethod
    def unique_targets(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        if any(len(user_id) != 26 for user_id in value):
            raise ValueError("target_user_ids 必须是用户 ID")
        if len(value) != len(set(value)):
            raise ValueError("target_user_ids 不得重复")
        return value


class TeachingActivityRunAction(BaseModel):
    expected_version: int = Field(ge=1)
    action: Literal["start", "pause", "resume", "complete", "cancel"]


class TeachingActivityRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    activity_version_id: str
    course_id: str
    class_id: str
    course_release_assignment_id: str | None
    course_release_id: str | None
    target_snapshot: dict[str, Any]
    run_snapshot: dict[str, Any]
    status: str
    scheduled_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_by: str
    idempotency_key: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class TeacherAnnotationCreate(BaseModel):
    target_type: Literal["activity", "evidence", "knowledge_point", "intervention"]
    target_id: str = Field(min_length=1, max_length=26)
    visibility: Literal["teacher_only", "student_visible"] = "teacher_only"
    status: Literal["draft", "published"] = "draft"
    annotation: str = Field(min_length=1, max_length=2000)


class TeacherAnnotationUpdate(BaseModel):
    expected_version: int = Field(ge=1)
    visibility: Literal["teacher_only", "student_visible"] | None = None
    status: Literal["draft", "published", "archived"] | None = None
    annotation: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_change(self) -> "TeacherAnnotationUpdate":
        if all(value is None for value in (self.visibility, self.status, self.annotation)):
            raise ValueError("至少提供一个需要更新的字段")
        return self


class TeacherAnnotationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    class_id: str
    target_type: str
    target_id: str
    visibility: str
    status: str
    annotation: str
    created_by: str
    published_at: datetime | None
    archived_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime
