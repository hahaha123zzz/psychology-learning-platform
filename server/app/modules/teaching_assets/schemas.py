from typing import Any, Literal

from pydantic import BaseModel, Field

AssetTemplate = Literal["explanation", "comparison", "variable_map", "table", "focus"]
AssetAction = Literal[
    "SHOW",
    "HIGHLIGHT",
    "REVEAL",
    "FOCUS",
    "COMPARE",
    "PLAY",
    "PAUSE",
    "RESET",
]


class TeachingAssetCreate(BaseModel):
    asset_key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    template: AssetTemplate
    release_id: str | None = Field(default=None, min_length=26, max_length=26)
    content: dict[str, Any] = Field(min_length=1)
    fallback_text: str = Field(min_length=1, max_length=4000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)
    allowed_actions: list[AssetAction] = Field(default_factory=lambda: ["SHOW"])


class TeachingAssetPublish(BaseModel):
    version: int = Field(ge=1)
    release_id: str = Field(min_length=26, max_length=26)


class TeachingAssetOut(BaseModel):
    id: str
    course_id: str
    release_id: str | None
    asset_key: str
    version_no: int
    template: str
    status: str
    content: dict[str, Any]
    fallback_text: str
    evidence_refs: list[str]
    allowed_actions: list[str]
    version: int
    created_by: str
    published_by: str | None
    published_at: str | None
    created_at: str
    updated_at: str
