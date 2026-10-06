from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Table, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, OwnedMixin

# Association table — plain sa.Table, no mapped class, no relationships
idea_source_items_table = Table(
    "idea_source_items",
    Base.metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True, default=uuid4),
    Column(
        "idea_id",
        PG_UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "source_item_id",
        PG_UUID(as_uuid=True),
        ForeignKey("source_items.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint("idea_id", "source_item_id", name="uq_idea_source_item"),
)


class Source(OwnedMixin, Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # 'rss', 'youtube', 'reddit', 'website', etc.
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSONB: API keys, filters, source-specific options
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # No cross-domain relationships — use service layer to join across domains


class SourceItem(Base):
    __tablename__ = "source_items"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # FK — plain column, no relationship()
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Stable external identifier (YouTube video ID, Reddit post ID, etc.)
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Fallback deduplication when external_id is absent
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSONB: author, published_at, engagement metrics, raw API response
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # No cross-domain relationships — use service layer to join across domains

    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_source_external_id"),
        Index("ix_source_items_content_hash", "content_hash"),
    )
