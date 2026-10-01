from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class CreateSourceRequest(BaseModel):
    name: str = Field(..., min_length=1)
    source_type: str = Field(default="rss")
    url: str | None = None
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateSourceRequest(BaseModel):
    name: str | None = None
    source_type: str | None = None
    url: str | None = None
    enabled: bool | None = None
    config: dict[str, Any] | None = None


class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    source_type: str
    url: str | None = None
    enabled: bool
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
