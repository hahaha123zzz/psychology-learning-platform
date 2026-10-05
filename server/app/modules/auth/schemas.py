from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserInfo(BaseModel):
    id: str
    email: str
    display_name: str
    status: str


class LoginResponse(BaseModel):
    user: UserInfo
    platform_roles: list[str]
    session_expires_at: datetime


class MeCourseMembership(BaseModel):
    course_id: str
    role: str
    status: str


class MeResponse(BaseModel):
    id: str
    display_name: str
    platform_roles: list[str]
    course_memberships: list[MeCourseMembership]
    capabilities: dict[str, bool]


class PreferencesPatch(BaseModel):
    version: int = Field(ge=1)
    hint_density: str | None = Field(default=None, pattern="^(standard|compact|guided)$")
    reduced_motion: bool | None = None
    font_scale: str | None = Field(default=None, pattern="^(100|115|130)$")
    notification_in_app: bool | None = None


class PreferencesOut(BaseModel):
    user_id: str
    preferences: dict[str, object]
    version: int
    updated_at: datetime


class NotificationOut(BaseModel):
    id: str
    kind: str
    title: str
    body: str
    payload: dict[str, object]
    read_at: datetime | None
    created_at: datetime


class RefreshResponse(BaseModel):
    session_expires_at: datetime


class RoleAssignmentCreate(BaseModel):
    user_id: str = Field(min_length=26, max_length=26)
    role: str = Field(pattern="^(teacher|assistant|course_designer|course_publisher)$")
    scope_type: str = Field(pattern="^(platform|course|class)$")
    scope_id: str | None = Field(default=None, min_length=26, max_length=26)
    reason: str = Field(min_length=8, max_length=500)


class RoleAssignmentRevoke(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=8, max_length=500)


class RoleAssignmentOut(BaseModel):
    id: str
    user_id: str
    user_email: str
    user_display_name: str
    role: str
    scope_type: str
    scope_id: str | None
    status: str
    version: int
    granted_by: str | None
    created_at: datetime
    updated_at: datetime


class RoleAssignmentTargetOut(BaseModel):
    id: str
    email: EmailStr
    display_name: str


class AdminJobRetryRequest(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=8, max_length=500)


class AdminJobOut(BaseModel):
    id: str
    kind: str
    status: str
    stage: str | None
    progress: int
    retryable: bool
    attempt_count: int
    version: int
    course_id: str
    has_error: bool
    created_at: datetime
    updated_at: datetime


class AdminJobRetryOut(BaseModel):
    id: str
    kind: str
    status: str
    stage: str | None
    retryable: bool
    attempt_count: int
    version: int
