from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MediaAssetType(str, PyEnum):
    """Media asset type — must match media_asset_type PostgreSQL ENUM."""
    IMAGE = "IMAGE"


class MediaAssetStatus(str, PyEnum):
    """Media asset status — must match media_asset_status PostgreSQL ENUM."""
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


class MediaAsset(Base):
    """
    Persistent representation for generated/attached media.
    Belongs strictly to an immutable ContentVersion.
    """
    __tablename__ = "media_assets"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    content_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_versions.id", ondelete="CASCADE"),
        nullable=False,
    )

    type: Mapped[MediaAssetType] = mapped_column(
        Enum(MediaAssetType, name="media_asset_type", create_type=True),
        nullable=False,
        default=MediaAssetType.IMAGE,
    )

    status: Mapped[MediaAssetStatus] = mapped_column(
        Enum(MediaAssetStatus, name="media_asset_status", create_type=True),
        nullable=False,
        default=MediaAssetStatus.READY,
    )

    storage_url: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False, default="image/png")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alt_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_asset_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
