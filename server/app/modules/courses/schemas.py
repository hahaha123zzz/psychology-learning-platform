from datetime import datetime

from pydantic import BaseModel, Field


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    term: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    timezone: str = Field(default="Asia/Shanghai", max_length=64)


class CourseUpdate(BaseModel):
    version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=100)
    term: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    timezone: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


class CourseOut(BaseModel):
    id: str
    title: str
    term: str
    description: str | None
    timezone: str
    status: str
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class MemberAdd(BaseModel):
    user_id: str = Field(min_length=26, max_length=26)
    role: str = Field(pattern="^(teacher|student|assistant)$")


class MemberRoleUpdate(BaseModel):
    version: int = Field(ge=1)
    role: str = Field(pattern="^(teacher|student|assistant)$")


class MemberOut(BaseModel):
    id: str
    user_id: str
    display_name: str
    role: str
    status: str
    joined_at: datetime
