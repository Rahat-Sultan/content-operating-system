from datetime import datetime
from uuid import UUID
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class StrategyConfigRequest(BaseModel):
    niche: str | None = None
    audience: str | None = None
    goals: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    tone: str | None = None
    voice_guidelines: str | None = None


class CreateStrategyRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    source_ids: list[UUID] = Field(default_factory=list)


class UpdateStrategyRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    source_ids: list[UUID] | None = None


class SourceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    source_type: str
    url: str | None = None
    enabled: bool


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    config: dict[str, Any]
    enabled: bool
    sources: list[SourceSummary] = Field(default_factory=list)
    schedule_info: dict[str, Any] | None = None
    archived_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class StrategyDiscoveryResult(BaseModel):
    strategy_id: UUID
    strategy_name: str
    sources_synced: int
    items_fetched: int
    new_items_count: int
    ideas_created_count: int
    created_idea_ids: list[UUID] = Field(default_factory=list)
