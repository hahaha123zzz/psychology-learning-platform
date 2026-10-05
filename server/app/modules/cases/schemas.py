from typing import Any, Literal

from pydantic import BaseModel, Field

CaseKey = Literal[
    "confound-basic",
    "experiment-decomposer",
    "design-board",
    "result-interpreter",
    "critique",
]


class CaseCreate(BaseModel):
    course_id: str = Field(min_length=26, max_length=26)
    case_key: CaseKey = "confound-basic"


class CaseResponse(BaseModel):
    version: int = Field(ge=1)
    draft: bool = False
    selected_confound: str = Field(default="", max_length=120)
    reasoning: str = Field(default="", max_length=2000)
    design_change: str = Field(default="", max_length=2000)


class CaseOut(BaseModel):
    id: str
    course_id: str
    case_key: str
    status: str
    case_snapshot: dict[str, Any]
    response: dict[str, Any] | None
    outcome: dict[str, Any] | None
    version: int
    created_at: str
    updated_at: str
