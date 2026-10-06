from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Table, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, OwnedMixin

# Association table — plain sa.Table, no mapped class, no relationships
strategy_sources_table = Table(
    "strategy_sources",
    Base.metadata,
    Column("id", PG_UUID(as_uuid=True), primary_key=True, default=uuid4),
    Column(
        "strategy_id",
        PG_UUID(as_uuid=True),
        ForeignKey("content_strategies.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "source_id",
        PG_UUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    UniqueConstraint("strategy_id", "source_id", name="uq_strategy_source"),
)


class ContentStrategy(OwnedMixin, Base):
    __tablename__ = "content_strategies"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSONB: audience, goals, platforms, content_types, topics, tone, voice_guidelines
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
