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


class RefreshResponse(BaseModel):
    session_expires_at: datetime
