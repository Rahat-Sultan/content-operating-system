from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class WorkflowRunStatus(str, PyEnum):
    """
    Workflow run status — values must match workflow_run_status PostgreSQL ENUM exactly.

    Active (non-terminal) statuses used in the partial unique index:
        PENDING, RUNNING, PAUSED, NEEDS_REVIEW, PUBLISHING

    Terminal statuses (allow a new run on the same idea):
        COMPLETED, FAILED, CANCELLED, REJECTED
    """
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    PUBLISHING = "PUBLISHING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class WorkflowRun(Base):
    """
    One production attempt for an Idea.
    WorkflowRun.id is passed directly as LangGraph thread_id — no separate thread_id column.
    Partial unique index uq_active_workflow_per_idea enforces one active run per idea.
    """
    __tablename__ = "workflow_runs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # FKs — plain columns, no cross-domain relationship()
    idea_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("ideas.id", ondelete="CASCADE"),
        nullable=False,
    )
    strategy_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_strategies.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[WorkflowRunStatus] = mapped_column(
        Enum(WorkflowRunStatus, name="workflow_run_status", create_type=True),
        nullable=False,
        default=WorkflowRunStatus.PENDING,
    )

    # Human-readable error for failed/cancelled runs — durable source of truth per WORKFLOW.md
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSONB: node execution history, timing, LangGraph resumption context
    run_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Same-domain relationships (Research and ContentBrief live in this module)
    research: Mapped["Research"] = relationship(
        "Research", back_populates="workflow_run", uselist=False
    )
    content_brief: Mapped["ContentBrief"] = relationship(
        "ContentBrief", back_populates="workflow_run", uselist=False
    )

    __table_args__ = (
        # Enforces one active production run per idea at the DB level.
        # Active statuses: PENDING, RUNNING, PAUSED, NEEDS_REVIEW, PUBLISHING
        Index(
            "uq_active_workflow_per_idea",
            "idea_id",
            unique=True,
            postgresql_where=(
                status.in_(["PENDING", "RUNNING", "PAUSED", "NEEDS_REVIEW", "PUBLISHING"])
            ),
        ),
    )


class Research(Base):
    """Structured research artifact for a workflow run — one per run."""
    __tablename__ = "research"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSONB: key_findings, important_claims, confidence
    findings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # JSONB: supporting sources with provenance (url, title, author, retrieved_at)
    sources: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Same-domain back-reference
    workflow_run: Mapped["WorkflowRun"] = relationship(
        "WorkflowRun", back_populates="research"
    )


class ContentBrief(Base):
    """Structured content brief produced by the Strategist node — one per run."""
    __tablename__ = "content_briefs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    workflow_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # JSONB: angle, hook, target_audience, key_points, structure, tone, cta, platform, content_goal
    brief: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Same-domain back-reference
    workflow_run: Mapped["WorkflowRun"] = relationship(
        "WorkflowRun", back_populates="content_brief"
    )
