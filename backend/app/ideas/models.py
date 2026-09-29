from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class IdeaStatus(str, PyEnum):
    """Idea lifecycle status values — must match idea_status PostgreSQL ENUM exactly."""
    NEW = "NEW"
    SELECTED = "SELECTED"
    IN_PROGRESS = "IN_PROGRESS"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class Idea(Base):
    __tablename__ = "ideas"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # FK — plain column, no relationship()
    strategy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_strategies.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[IdeaStatus] = mapped_column(
        Enum(IdeaStatus, name="idea_status", create_type=True),
        nullable=False,
        default=IdeaStatus.NEW,
    )

    # Five scoring dimensions produced by one structured LLM call (0.000–1.000)
    relevance_score: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=3), nullable=True)
    trend_score: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=3), nullable=True)
    novelty_score: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=3), nullable=True)
    audience_fit_score: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=3), nullable=True)
    source_quality_score: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=3), nullable=True)

    # Weighted final score computed by application code, not the LLM
    final_score: Mapped[float | None] = mapped_column(Numeric(precision=4, scale=3), nullable=True)

    # JSONB: raw LLM scoring output, rationale, any extra discovery context
    scoring_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

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
