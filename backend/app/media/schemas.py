from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class GenerateMediaRequest(BaseModel):
    prompt: str | None = None
    regenerate: bool = False


class MediaAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    content_version_id: UUID
    type: str
    status: str
    storage_url: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    alt_text: str | None = None
    prompt: str
    provider: str
    provider_asset_id: str | None = None
    asset_metadata: dict = {}
    created_at: datetime
    updated_at: datetime
