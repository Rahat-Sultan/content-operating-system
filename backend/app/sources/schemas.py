from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class CreateSourceRequest(BaseModel):
    # Optional: when blank, the source is named after its link.
    name: str | None = None
    source_type: str = Field(default="rss")
    url: str | None = None
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class UpdateSourceRequest(BaseModel):
    # Blank or missing keeps the current name. A source with a link is named after the link.
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
