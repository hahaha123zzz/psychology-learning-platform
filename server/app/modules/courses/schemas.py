from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema

_DOMAIN_PACK_JSON_SCHEMA = {
    "type": "object",
    "description": "由课程服务进行对象引用、Relation DAG 与教材证据的语义校验。",
    "properties": {
        "chapters": {"type": "array", "items": {"type": "string"}},
        "knowledge_points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "minLength": 1},
                    "title": {"type": "string", "minLength": 1},
                    "evidence_binding_keys": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "required": ["key", "title"],
                "additionalProperties": False,
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "minLength": 1},
                    "source_key": {"type": "string", "minLength": 1},
                    "target_key": {"type": "string", "minLength": 1},
                    "relation_type": {"type": "string", "enum": ["prerequisite"]},
                    "evidence_binding_keys": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "required": ["source_key", "target_key", "relation_type"],
                "additionalProperties": False,
            },
        },
        "experiments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "minLength": 1},
                    "title": {"type": "string", "minLength": 1},
                    "research_question": {"type": ["string", "null"], "maxLength": 4000},
                    "hypothesis": {"type": ["string", "null"], "maxLength": 4000},
                    "iv": {"type": ["string", "null"], "maxLength": 4000},
                    "dv": {"type": ["string", "null"], "maxLength": 4000},
                    "operationalization": {"type": ["string", "null"], "maxLength": 4000},
                    "controls": {
                        "anyOf": [
                            {"type": "null"},
                            {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1, "maxLength": 1000},
                                "maxItems": 50,
                            },
                        ]
                    },
                    "confounds": {
                        "anyOf": [
                            {"type": "null"},
                            {
                                "type": "array",
                                "items": {"type": "string", "minLength": 1, "maxLength": 1000},
                                "maxItems": 50,
                            },
                        ]
                    },
                    "design": {"type": ["string", "null"], "maxLength": 4000},
                    "procedure": {"type": ["string", "null"], "maxLength": 4000},
                    "prediction": {"type": ["string", "null"], "maxLength": 4000},
                    "result_pattern": {"type": ["string", "null"], "maxLength": 4000},
                    "interpretation": {"type": ["string", "null"], "maxLength": 4000},
                    "limitations": {"type": ["string", "null"], "maxLength": 4000},
                    "textbook_evidence": {
                        "type": ["array", "null"],
                        "description": (
                            "EvidenceBinding 稳定 key 数组；与 evidence_binding_keys 等价。"
                        ),
                        "items": {"type": "string", "minLength": 1},
                    },
                    "knowledge_point_keys": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "evidence_binding_keys": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "required": ["key", "title"],
                "additionalProperties": False,
            },
        },
        "misconceptions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "minLength": 1},
                    "title": {"type": "string", "minLength": 1},
                    "knowledge_point_keys": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                    "evidence_binding_keys": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                    },
                },
                "required": ["key", "title"],
                "additionalProperties": False,
            },
        },
        "evidence_bindings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "minLength": 1},
                    "object_key": {"type": "string", "minLength": 1},
                    "material_id": {"type": "string", "minLength": 1},
                    "material_version_id": {"type": "string", "minLength": 1},
                    "source_object_id": {"type": "string", "minLength": 1},
                },
                "required": [
                    "key",
                    "object_key",
                    "material_id",
                    "material_version_id",
                    "source_object_id",
                ],
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}
DomainPack = Annotated[dict, WithJsonSchema(_DOMAIN_PACK_JSON_SCHEMA)]


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


class ClassCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)


class ClassOut(BaseModel):
    id: str
    course_id: str
    code: str
    name: str
    status: str
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime


class TeacherAssignmentCreate(BaseModel):
    teacher_id: str = Field(min_length=26, max_length=26)
    assignment_role: str = Field(default="lead", pattern="^(lead|assistant)$")


class TeacherAssignmentOut(BaseModel):
    id: str
    class_id: str
    teacher_id: str
    teacher_name: str
    assignment_role: str
    status: str
    version: int
    assigned_by: str
    created_at: datetime


class AdminClassTeacherAssignmentCreate(BaseModel):
    class_id: str = Field(min_length=26, max_length=26)
    teacher_id: str = Field(min_length=26, max_length=26)
    assignment_role: str = Field(default="lead", pattern="^(lead|assistant)$")
    reason: str = Field(min_length=8, max_length=500)


class AdminClassTeacherAssignmentEnd(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=8, max_length=500)


class AdminCourseClassCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=8, max_length=500)


class AdminCourseMemberCreate(BaseModel):
    user_id: str = Field(min_length=26, max_length=26)
    role: str = Field(pattern="^(teacher|student|assistant)$")
    reason: str = Field(min_length=8, max_length=500)


class AdminClassMemberCreate(BaseModel):
    user_id: str = Field(min_length=26, max_length=26)
    reason: str = Field(min_length=8, max_length=500)


class AdminMembershipRemove(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=8, max_length=500)


class ClassMemberAdd(BaseModel):
    user_id: str = Field(min_length=26, max_length=26)


class ClassMemberOut(BaseModel):
    id: str
    class_id: str
    user_id: str
    display_name: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ReleaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    material_ids: list[str] = Field(default_factory=list, max_length=50)
    domain_release_id: str | None = Field(default=None, min_length=26, max_length=26)
    domain_pack: DomainPack = Field(default_factory=dict)
    pedagogy_pack: dict = Field(default_factory=dict)
    assessment_pack: dict = Field(default_factory=dict)


class ReleaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    material_ids: list[str] | None = Field(default=None, max_length=50)
    domain_release_id: str | None = Field(default=None, min_length=26, max_length=26)
    domain_pack: DomainPack | None = None
    pedagogy_pack: dict | None = None
    assessment_pack: dict | None = None


class ReleaseOut(BaseModel):
    id: str
    course_id: str
    version_no: int
    name: str
    status: str
    domain_release_id: str | None
    manifest: dict
    version: int
    created_by: str
    published_by: str | None
    published_at: datetime | None
    deprecated_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ReleaseAssignmentSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_release_id: str = Field(min_length=26, max_length=26)
    expected_version: int = Field(ge=0)
    close_reason: str | None = Field(default=None, max_length=500)


class ReleaseAssignmentOut(BaseModel):
    id: str
    course_id: str
    class_id: str
    course_release_id: str
    status: str
    version: int
    assigned_by: str
    assigned_at: datetime
    supersedes_id: str | None
    closed_by: str | None
    closed_at: datetime | None
    close_reason: str | None


class ReleasePreviewOut(BaseModel):
    release: ReleaseOut
    manifest_sha256: str


class ReleaseReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    manifest_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    decision: str = Field(pattern="^(approved|changes_requested|rejected)$")
    reason: str = Field(min_length=1, max_length=2000)


class ReleasePublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    warning_reason: str | None = Field(default=None, min_length=1, max_length=2000)
