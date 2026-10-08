from datetime import datetime, timezone
import logging
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.content.models import Approval, ApprovalStatus, Content, ContentVersion
from app.workflows.models import WorkflowRun, WorkflowRunStatus
from app.publishing.models import Publication, PublicationStatus
from app.publishing.interface import (
    PublisherInterface,
    PublishRequest,
    PublishResult,
    TransientPublishingError,
    PermanentPublishingError,
    AmbiguousTimeoutPublishingError,
    PublishingError,
)
from app.publishing.factory import get_publisher_provider
from app.analytics.stub_provider import record_stub_analytics

logger = logging.getLogger(__name__)


def build_idempotency_key(content_version_id: UUID, platform: str) -> str:
    """
    Deterministic idempotency key identifying the logical publication:
    f"{content_version_id}:{platform}"
    Crucial: retries reuse the exact same key.
    """
    return f"{content_version_id}:{platform}"


class PublishingService:
    """
    Publishing domain service:
    1. Validates ContentVersion lock, workflow run ownership, and approved status.
    2. Atomically manages the Publication lifecycle (PENDING -> PUBLISHING -> PUBLISHED / FAILED).
    3. Handles database-level uniqueness collisions safely (concurrent publications return existing winner).
    4. Supports bounded retry of transient provider failures reusing the exact same idempotency key.
    """

    def __init__(self, provider: PublisherInterface | None = None):
        self.provider = provider or get_publisher_provider()

    def publish_content_version(
        self,
        db: Session,
        workflow_run_id: UUID,
        content_version_id: UUID,
        platform: str = "linkedin",
        max_transient_retries: int = 3,
        request_metadata: dict[str, Any] | None = None,
    ) -> Publication:
        """
        Executes publication of an approved ContentVersion for a WorkflowRun.
        Guarantees idempotency and PostgreSQL-enforced uniqueness.
        """
        # -------------------------------------------------------------
        # STEP 1: Content Version & Workflow Run Lock Verification
        # -------------------------------------------------------------
        version = db.query(ContentVersion).filter(ContentVersion.id == content_version_id).first()
        if not version:
            raise ValueError(f"ContentVersion {content_version_id} does not exist.")

        content = db.query(Content).filter(Content.id == version.content_id).first()
        if not content:
            raise ValueError(f"Content container for version {content_version_id} not found.")

        if content.workflow_run_id != workflow_run_id:
            raise ValueError(
                f"Version {content_version_id} belongs to workflow run {content.workflow_run_id}, "
                f"not requested run {workflow_run_id}."
            )

        run = db.query(WorkflowRun).filter(WorkflowRun.id == workflow_run_id).first()
        if not run:
            raise ValueError(f"WorkflowRun {workflow_run_id} does not exist.")

        # Reject publication if workflow is REJECTED or CANCELLED
        if run.status in (WorkflowRunStatus.REJECTED, WorkflowRunStatus.CANCELLED):
            raise ValueError(f"Cannot publish: WorkflowRun {workflow_run_id} is in status '{run.status.value}'.")

        # Verify Approval record exists and status is APPROVED
        approval = (
            db.query(Approval)
            .filter(Approval.content_version_id == content_version_id)
            .first()
        )
        if not approval:
            raise ValueError(f"ContentVersion {content_version_id} has no approval record. Cannot publish unapproved draft.")

        if approval.status != ApprovalStatus.APPROVED:
            raise ValueError(
                f"ContentVersion {content_version_id} was not approved (decision: '{approval.status.value}'). Cannot publish."
            )

        # Confirm this version is indeed the latest version of the Content container
        latest_version = (
            db.query(ContentVersion)
            .filter(ContentVersion.content_id == content.id)
            .order_by(ContentVersion.version_number.desc())
            .first()
        )
        if latest_version and latest_version.id != content_version_id:
            raise ValueError(
                f"Stale ContentVersion: requested version is v{version.version_number} ({content_version_id}), "
                f"but latest version is v{latest_version.version_number} ({latest_version.id}). Stale versions cannot publish."
            )

        # Resolve the public image URL before any write, so a configuration error fails cleanly.
        from app.media.public_url import public_image_url_for_version
        image_url = public_image_url_for_version(db, version.id)
        if image_url:
            request_metadata = {**(request_metadata or {}), "image_url": image_url}

        # -------------------------------------------------------------
        # STEP 2: Durable Publication State & Idempotency Key
        # -------------------------------------------------------------
        idempotency_key = build_idempotency_key(content_version_id, platform)

        # Check existing publication record
        existing = db.query(Publication).filter(Publication.idempotency_key == idempotency_key).first()
        if existing:
            if existing.status == PublicationStatus.PUBLISHED:
                logger.info(
                    "Publication for key '%s' is already PUBLISHED (id: %s, external_id: %s). Reusing existing record.",
                    idempotency_key,
                    existing.id,
                    existing.external_id,
                )
                return existing

            # If existing publication previously failed or is pending, we reuse the existing row
            publication = existing
            publication.status = PublicationStatus.PUBLISHING
            publication.error = None
            db.commit()
            db.refresh(publication)
        else:
            # Create new Publication row in PENDING/PUBLISHING status
            pub_id = uuid4()
            from app.workflows.models import WorkflowRun as _Run
            run_owner = db.query(_Run.owner_id).filter(_Run.id == workflow_run_id).scalar()
            publication = Publication(
                id=pub_id,
                owner_id=run_owner,
                content_version_id=content_version_id,
                platform=platform,
                status=PublicationStatus.PUBLISHING,
                idempotency_key=idempotency_key,
                publication_metadata={
                    "workflow_run_id": str(workflow_run_id),
                    "version_number": version.version_number,
                },
            )
            db.add(publication)
            try:
                db.commit()
                db.refresh(publication)
            except IntegrityError:
                # Concurrent publication attempt already inserted this idempotency key!
                db.rollback()
                winner = db.query(Publication).filter(Publication.idempotency_key == idempotency_key).first()
                if winner:
                    logger.info("Concurrent insert caught by unique constraint; returning winning publication %s", winner.id)
                    return winner
                raise

        # -------------------------------------------------------------
        # STEP 3: Provider Invocation with Bounded Retry
        # -------------------------------------------------------------
        publish_req = PublishRequest(
            workflow_run_id=workflow_run_id,
            content_version_id=content_version_id,
            platform=platform,
            title=version.title,
            body=version.body,
            idempotency_key=idempotency_key,
            metadata=request_metadata or {},
        )

        attempts = 0
        last_error: Exception | None = None

        while attempts < max_transient_retries:
            attempts += 1
            try:
                logger.info(
                    "Publishing attempt %d/%d for publication %s (key: %s)",
                    attempts,
                    max_transient_retries,
                    publication.id,
                    idempotency_key,
                )
                pub_result = self.provider.publish(publish_req)
                
                # Success! Transition to PUBLISHED
                publication.status = PublicationStatus.PUBLISHED
                publication.external_id = pub_result.external_post_id
                publication.url = pub_result.url
                publication.published_at = pub_result.published_at
                publication.publication_metadata = {
                    **publication.publication_metadata,
                    **pub_result.provider_metadata,
                    "attempts": attempts,
                }
                publication.error = None
                # The idea moves to Published in the same commit as the publication.
                from app.ideas.lifecycle import advance_idea
                from app.ideas.models import IdeaStatus
                advance_idea(
                    db, run.idea_id, run.owner_id, IdeaStatus.PUBLISHED,
                    [IdeaStatus.NEW, IdeaStatus.SELECTED, IdeaStatus.IN_PROGRESS],
                )
                db.commit()
                db.refresh(publication)

                # Record stub analytics metrics
                try:
                    record_stub_analytics(db=db, publication_id=publication.id)
                except Exception as a_exc:
                    logger.warning("Failed to record analytics for publication %s: %s", publication.id, a_exc)

                return publication

            except TransientPublishingError as t_exc:
                logger.warning(
                    "Transient error on attempt %d for publication %s: %s",
                    attempts,
                    publication.id,
                    t_exc,
                )
                last_error = t_exc
                if attempts >= max_transient_retries:
                    break
                continue

            except AmbiguousTimeoutPublishingError as a_exc:
                logger.error(
                    "Ambiguous timeout for publication %s (key %s): %s. Stopping retries to prevent duplicate external dispatch.",
                    publication.id,
                    idempotency_key,
                    a_exc,
                )
                last_error = a_exc
                break

            except (PermanentPublishingError, Exception) as p_exc:
                logger.error(
                    "Permanent or unexpected publishing failure for publication %s: %s",
                    publication.id,
                    p_exc,
                )
                last_error = p_exc
                break

        # If we reached here, publication failed
        publication.status = PublicationStatus.FAILED
        publication.error = f"{type(last_error).__name__}: {str(last_error)}"
        publication.publication_metadata = {
            **publication.publication_metadata,
            "attempts": attempts,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        db.commit()
        db.refresh(publication)
        raise last_error or PublishingError(f"Publishing failed after {attempts} attempts.")
