from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NoteType = Literal["episodic", "semantic", "working"]
NoteSource = Literal["manual", "conversation", "import"]


class SM2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ease: float = Field(default=2.5, ge=1.3)
    interval: int = Field(default=1, ge=1)
    next_review: date


class NoteFrontmatter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}-[a-z0-9-]+$")
    type: NoteType
    created: datetime
    last_access: datetime
    access_count: int = Field(ge=0)
    strength: float = Field(ge=0.0, le=1.0)
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sm2: SM2 | None = None
    source: NoteSource = "manual"
