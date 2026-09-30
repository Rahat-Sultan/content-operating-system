from datetime import datetime, timezone
import logging
from uuid import uuid4
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.graph.state import ContentGraphState
from app.content.models import ContentVersion
from app.publishing.models import Publication, PublicationStatus
from app.publishing.stub_provider import execute_publish
from app.analytics.stub_provider import record_stub_analytics

logger = logging.getLogger(__name__)


def publisher_node(state: ContentGraphState) -> dict:
    """
    Publisher node in the Content Graph:
    1. Reads current_content_version_id from state.
    2. Loads the approved content version from the database.
    3. Builds an idempotency key: f"{content_version_id}:linkedin".
    4. Calls the publishing stub provider to simulate platform posting.
    5. Inserts a Publication row into PostgreSQL with status = 'PUBLISHED'.
    6. Generates and records stub analytics metrics for the new publication.
    7. Returns updated state containing publication_id.
    """
    content_version_id = state.get("current_content_version_id")
    workflow_run_id = state.get("workflow_run_id")

    if not content_version_id:
        raise ValueError(f"Cannot publish: no current_content_version_id in state for run {workflow_run_id}")

    platform = "linkedin"
    idempotency_key = f"{content_version_id}:{platform}"

    db: Session = SessionLocal()
    try:
        # Load content version
        version = db.query(ContentVersion).filter(ContentVersion.id == content_version_id).first()
        if not version:
            raise ValueError(f"ContentVersion {content_version_id} not found in database.")

        logger.info(
            "Publisher node publishing version %s to platform '%s' (run %s)",
            content_version_id,
            platform,
            workflow_run_id,
        )

        # Call publishing stub provider
        pub_result = execute_publish(
            content_version_id=content_version_id,
            title=version.title,
            body=version.body,
            platform=platform,
        )

        # Insert publication record
        pub_id = uuid4()
        publication = Publication(
            id=pub_id,
            content_version_id=content_version_id,
            platform=platform,
            status=PublicationStatus.PUBLISHED,
            idempotency_key=idempotency_key,
            external_id=pub_result.get("external_post_id"),
            url=pub_result.get("url"),
            publication_metadata={
                "is_stub": True,
                "platform_response": pub_result.get("platform_response", {}),
            },
            published_at=datetime.now(timezone.utc),
        )
        db.add(publication)
        db.commit()
        db.refresh(publication)

        logger.info(
            "Publication created successfully with id %s and idempotency_key '%s'",
            pub_id,
            idempotency_key,
        )

        # Record initial stub analytics row
        analytics = record_stub_analytics(db=db, publication_id=pub_id)
        logger.info(
            "Initial analytics recorded for publication %s (metrics: %s)",
            pub_id,
            analytics.metrics,
        )

        return {
            "publication_id": pub_id,
        }
    except Exception as exc:
        db.rollback()
        logger.error("Publisher node failed: %s", exc, exc_info=True)
        raise
    finally:
        db.close()
