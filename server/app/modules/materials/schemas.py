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
