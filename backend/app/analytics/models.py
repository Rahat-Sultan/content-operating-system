from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Analytics(Base):
    """
    Performance snapshot for a publication.
    Multiple rows per publication are allowed — supports historical snapshots over time.
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
    # No cross-domain relationships — use service layer to join across domains
