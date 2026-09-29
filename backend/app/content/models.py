from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ContentVersionOrigin(str, PyEnum):
    """Origin of a content version — must match content_version_origin PostgreSQL ENUM exactly."""
    WRITER_AGENT = "WRITER_AGENT"
    HUMAN_EDIT = "HUMAN_EDIT"


class ApprovalStatus(str, PyEnum):
    """Approval decision — must match approval_status PostgreSQL ENUM exactly."""
    APPROVED = "APPROVED"
    REVISION_REQUESTED = "REVISION_REQUESTED"
    REJECTED = "REJECTED"


class Content(Base):
    """
    Logical content object — container for all versions produced by a workflow run.
    One Content per WorkflowRun (enforced by unique constraint on workflow_run_id).
    """
    __tablename__ = "content"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    # FK — plain column, no cross-domain relationship()
    workflow_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Same-domain relationships
    versions: Mapped[list["ContentVersion"]] = relationship(
        "ContentVersion",
        back_populates="content",
        order_by="ContentVersion.version_number",
    )


class ContentVersion(Base):
    """
    Immutable content version — never updated, only inserted.
    Every write (agent generation or human edit) creates a new row.
    UNIQUE(content_id, version_number) enforced at DB level.
    """
    __tablename__ = "content_versions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    content_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content.id", ondelete="CASCADE"),
        nullable=False,
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)

    origin: Mapped[ContentVersionOrigin] = mapped_column(
        Enum(ContentVersionOrigin, name="content_version_origin", create_type=True),
        nullable=False,
        default=ContentVersionOrigin.WRITER_AGENT,
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Same-domain relationships
    content: Mapped["Content"] = relationship("Content", back_populates="versions")
    approval: Mapped["Approval | None"] = relationship(
        "Approval", back_populates="content_version", uselist=False
    )

    __table_args__ = (
        UniqueConstraint("content_id", "version_number", name="uq_content_version_number"),
    )


class Approval(Base):
    """
    Human approval decision tied to exactly one ContentVersion.
    Approval requests must carry content_version_id — backend rejects stale requests (409).
    """
    __tablename__ = "approvals"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    content_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("content_versions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, name="approval_status", create_type=True),
        nullable=False,
    )

    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Will become user_id FK when auth is added
    approved_by: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Same-domain back-reference
    content_version: Mapped["ContentVersion"] = relationship(
        "ContentVersion", back_populates="approval"
    )
