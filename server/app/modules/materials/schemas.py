from pydantic import BaseModel, Field


class MaterialUploadForm(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    material_type: str = Field(
        pattern="^(textbook|slides|handout|exercise|reference|other)$"
    )
    visibility: str = Field(default="draft", pattern="^(draft|published)$")


class MaterialUploadOut(BaseModel):
    material_id: str
    version_id: str
    status: str
    sha256: str
    size_bytes: int


class KnowledgeObjectCorrection(BaseModel):
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    normalized_content: str | None = None
    reading_order: int | None = Field(default=None, ge=0)
    review_status: str | None = Field(
        default=None, pattern="^(pending|approved|rejected|corrected)$"
    )
