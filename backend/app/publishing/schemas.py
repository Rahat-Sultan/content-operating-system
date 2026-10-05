from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict
from app.publishing.models import PublicationStatus


class PublicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content_version_id: UUID
    platform: str
    status: PublicationStatus
    idempotency_key: str
    external_id: str | None = None
    url: str | None = None
    publication_metadata: dict[str, Any]
    error: str | None = None
    created_at: datetime
    published_at: datetime | None = None
    schedule_info: dict[str, Any] | None = None


class AnalyticsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    publication_id: UUID
    metrics: dict[str, Any]
    collected_at: datetime
