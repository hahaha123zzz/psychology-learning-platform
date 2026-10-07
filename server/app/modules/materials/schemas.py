from typing import Any, Literal

from pydantic import BaseModel, Field


class MaterialUploadForm(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    material_type: str = Field(pattern="^(textbook|slides|handout|exercise|reference|other)$")
    visibility: str = Field(default="draft", pattern="^(draft|published)$")


class MaterialUploadOut(BaseModel):
    material_id: str
    version_id: str
    status: str
    sha256: str
    size_bytes: int


class MaterialProvenanceUpdate(BaseModel):
    """提交者自报的版本来源信息；字段本身不代表来源已经核验。"""

    version: int = Field(ge=1)
    source_title: str | None = Field(default=None, max_length=300, description="自报来源标题")
    publisher: str | None = Field(default=None, max_length=200, description="自报出版方")
    content_author: str | None = Field(default=None, max_length=200, description="自报内容作者")
    edition: str | None = Field(default=None, max_length=100, description="自报版次")
    source_url: str | None = Field(
        default=None, max_length=1000, pattern=r"^https?://\S+$"
    )
    license: str | None = Field(default=None, max_length=200, description="自报许可信息")
    course_resource_role: str | None = Field(
        default=None,
        pattern="^(course_textbook|supplementary_resource)$",
        description="课程内部用途指定，不代表外部认证或教材权威性",
    )


class MaterialProvenanceReview(BaseModel):
    """课程内对自报元数据的复核，不构成外部来源核验或教材权威性认证。"""

    version: int = Field(ge=1)
    status: str = Field(
        pattern="^(verified|rejected)$",
        description="verified 仅表示不同的课程 teacher/course_publisher 已复核自报信息",
    )
    note: str = Field(min_length=1, max_length=1000)


class MaterialProvenanceRead(BaseModel):
    source_title: str | None
    publisher: str | None
    content_author: str | None
    edition: str | None
    source_url: str | None
    license: str | None
    course_resource_role: Literal["course_textbook", "supplementary_resource"] | None = Field(
        description="课程内部用途分类；null 表示未分类，不依据标题或材料类型推断"
    )
    status: Literal["unreviewed", "verified", "rejected"] = Field(
        description="verified 仅表示课程内不同教师/发布者复核自报信息，不代表外部核验"
    )
    version: int
    submitted_by: str | None = None
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_note: str | None = None


class MaterialProvenancePointerRead(BaseModel):
    """学生引用中的安全来源投影；不含提交者、审核者或审核备注。"""

    source_title: str | None
    publisher: str | None
    content_author: str | None
    edition: str | None
    source_url: str | None
    license: str | None
    course_resource_role: Literal["course_textbook", "supplementary_resource"] | None
    status: Literal["unreviewed", "verified", "rejected"]
    version: int


class MaterialVersionListRead(BaseModel):
    id: str
    version_no: int
    status: str
    size_bytes: int | None
    content_type: str | None
    provenance: MaterialProvenanceRead | None = None
    quality_gate_status: str | None = None
    workflow_state: str | None = None
    published_snapshot_id: str | None = None


class CourseMaterialListRead(BaseModel):
    id: str
    title: str
    material_type: str
    status: str
    created_at: str
    current_version: MaterialVersionListRead | None
    learning_version: MaterialVersionListRead | None = None
    visibility: str | None = None


class CourseMaterialsResponse(BaseModel):
    data: list[CourseMaterialListRead]
    meta: dict[str, Any]


class MaterialProvenanceResult(BaseModel):
    material_version_id: str
    provenance: MaterialProvenanceRead


class MaterialProvenanceResponse(BaseModel):
    data: MaterialProvenanceResult
    meta: dict[str, Any]


class KnowledgeObjectCorrection(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    normalized_content: str | None = None
    reading_order: int | None = Field(default=None, ge=0)
    review_status: str | None = Field(
        default=None, pattern="^(pending|approved|rejected|corrected)$"
    )


class ParseReviewIssueResolution(BaseModel):
    status: str = Field(pattern="^(resolved|ignored)$")
    resolution: str = Field(min_length=1, max_length=1000)


class UploadSessionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    material_type: str = Field(pattern="^(textbook|slides|handout|exercise|reference|other)$")
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)


class UploadPartComplete(BaseModel):
    etag: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(gt=0)
