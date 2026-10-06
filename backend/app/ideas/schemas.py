from datetime import datetime
from uuid import UUID
from typing import Any
from pydantic import BaseModel, ConfigDict
from app.ideas.models import IdeaStatus


class IdeaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strategy_id: UUID
    title: str
    description: str | None = None
    status: IdeaStatus
    relevance_score: float | None = None
    trend_score: float | None = None
    novelty_score: float | None = None
    audience_fit_score: float | None = None
    source_quality_score: float | None = None
    final_score: float | None = None
    scoring_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    # Target platforms of the idea's strategy (lower case). Empty when the strategy has none.
    platforms: list[str] = []


class SourceItemSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_id: UUID
    external_id: str | None = None
    title: str | None = None
    url: str | None = None
    content: str | None = None
    source_metadata: dict[str, Any]
    collected_at: datetime

