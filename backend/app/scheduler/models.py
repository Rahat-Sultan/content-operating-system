import enum
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WorkerHeartbeat(Base):
    """
    One row per scheduler process, refreshed on every loop. Lets the UI tell
    whether automatic analytics sync is actually running.
    """
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(Text, primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class JobType(str, enum.Enum):
    DISCOVERY = "DISCOVERY"
    ANALYTICS_SYNC = "ANALYTICS_SYNC"


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ScheduledJob(Base):
    """
    Durable PostgreSQL-backed job queue for scheduled discovery and analytics sync.
    Supports atomic multi-worker claiming via SELECT ... FOR UPDATE SKIP LOCKED
    and leases for crash recovery.
    """
    __tablename__ = "scheduled_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_type: Mapped[JobType] = mapped_column(
        Enum(JobType, name="job_type", create_type=True),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", create_type=True),
        nullable=False,
        default=JobStatus.PENDING,
    )

    # Polymorphic target IDs
    strategy_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_strategies.id", ondelete="CASCADE"),
        nullable=True,
    )
    publication_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("publications.id", ondelete="CASCADE"),
        nullable=True,
    )

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Job parameters & results
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_scheduled_jobs_status_scheduled_at", "status", "scheduled_at"),
        Index("ix_scheduled_jobs_strategy_id", "strategy_id"),
        Index("ix_scheduled_jobs_publication_id", "publication_id"),
    )
