from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, OwnedMixin


class PublicationStatus(str, PyEnum):
    """Publication status — must match publication_status PostgreSQL ENUM exactly."""
    PENDING = "PENDING"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class Publication(OwnedMixin, Base):
    """
    Publication record for a content version to a platform.
    idempotency_key (UNIQUE) prevents duplicate publications caused by retries.
    """
    __tablename__ = "publications"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # FK — plain column, no cross-domain relationship()
    content_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_versions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 'medium', 'substack', 'wordpress', etc.
    platform: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[PublicationStatus] = mapped_column(
        Enum(PublicationStatus, name="publication_status", create_type=True),
        nullable=False,
        default=PublicationStatus.PENDING,
    )

    # UNIQUE constraint via unique=True — prevents double-publish on retry
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)

    # Platform-assigned ID after successful publish
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Public URL of the published piece
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSONB: raw platform API response, publish request payload
    publication_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # No cross-domain relationships — use service layer to join across domains

    __table_args__ = (
        # "Does this version have a publication?" (the run page's publication lookup)
        # filtered on this with no index — a full table scan on every run page view.
        Index("ix_publications_content_version_id", "content_version_id"),
    )
