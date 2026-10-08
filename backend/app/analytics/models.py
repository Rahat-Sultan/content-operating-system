from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Analytics(Base):
    """
    Performance snapshot for a publication.
    Multiple rows per publication are allowed — supports historical snapshots over time.
    Partial unique index uq_initial_analytics_per_publication ensures only ONE initial
    snapshot (metrics->>'is_initial' = 'true') can exist per publication, preventing
    concurrent publish-time race duplicates.
    """
    __tablename__ = "analytics"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # FK — plain column, no cross-domain relationship()
    publication_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=False,
    )

    # JSONB: views, reads, engagement, shares, clicks — structure varies by platform
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "uq_initial_analytics_per_publication",
            "publication_id",
            unique=True,
            postgresql_where=text("((metrics->>'is_initial')::boolean IS TRUE)"),
        ),
        # Every "snapshots for this post" and "latest snapshot per post" query filters on
        # publication_id and orders by collected_at; without this, both were a full scan.
        # A plain ascending index serves the DESC order too (Postgres scans it backward).
        Index("ix_analytics_publication_id_collected_at", "publication_id", "collected_at"),
    )
