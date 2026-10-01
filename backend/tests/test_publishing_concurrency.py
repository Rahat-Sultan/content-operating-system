#!/usr/bin/env python3
"""
Concurrency and Idempotency Tests for Content OS Publishing (Phase 11: Tests 1-10).
Exercises real PostgreSQL database constraints, atomic state machine, bounded retries,
and version locks.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import sys
from uuid import uuid4

import psycopg
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, SessionLocal
from app.strategies.models import ContentStrategy  # noqa: F401
from app.sources.models import Source, SourceItem  # noqa: F401
from app.ideas.models import Idea  # noqa: F401
from app.content.models import Approval, ApprovalStatus, Content, ContentVersion, ContentVersionOrigin
from app.workflows.models import WorkflowRun, WorkflowRunStatus
from app.publishing.models import Publication, PublicationStatus
from app.analytics.models import Analytics
from app.publishing.service import PublishingService, build_idempotency_key
from app.publishing.local_provider import LocalTestPublisher
from app.publishing.interface import (
    TransientPublishingError,
    PermanentPublishingError,
    AmbiguousTimeoutPublishingError,
)


def get_raw_pg_conn():
    conn_str = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    return psycopg.connect(conn_str)


def seed_test_workflow_tree(db: Session, run_status: WorkflowRunStatus = WorkflowRunStatus.RUNNING, approved: bool = True):
    """
    Creates a full isolated test tree: Strategy -> Idea -> WorkflowRun -> Content -> ContentVersion (v1) -> Approval.
    """
    # 1. Strategy & Idea via raw SQL or db query
    conn = get_raw_pg_conn()
    cur = conn.cursor()
    strat_id = uuid4()
    cur.execute(
        "INSERT INTO content_strategies (id, name, description, config, enabled) VALUES (%s, %s, %s, %s, true)",
        (strat_id, f"Test Strat {strat_id.hex[:6]}", "Testing", "{}"),
    )
    idea_id = uuid4()
    cur.execute(
        "INSERT INTO ideas (id, strategy_id, title, status, scoring_metadata) VALUES (%s, %s, %s, %s, %s)",
        (idea_id, strat_id, f"Test Idea {idea_id.hex[:6]}", "SELECTED", "{}"),
    )
    conn.commit()
    cur.close()
    conn.close()

    # 2. WorkflowRun
    run = WorkflowRun(
        id=uuid4(),
        idea_id=idea_id,
        strategy_id=strat_id,
        status=run_status,
        run_metadata={},
    )
    db.add(run)
    db.commit()

    # 3. Content
    content = Content(
        id=uuid4(),
        workflow_run_id=run.id,
    )
    db.add(content)
    db.commit()

    # 4. ContentVersion v1
    v1 = ContentVersion(
        id=uuid4(),
        content_id=content.id,
        version_number=1,
        origin=ContentVersionOrigin.WRITER_AGENT,
        title="Test Post Title",
        body="This is an idempotent publication test body.",
    )
    db.add(v1)
    db.commit()

    # 5. Approval
    if approved:
        approval = Approval(
            id=uuid4(),
            content_version_id=v1.id,
            status=ApprovalStatus.APPROVED,
            feedback="LGTM",
        )
        db.add(approval)
        db.commit()

    db.refresh(run)
    db.refresh(content)
    db.refresh(v1)
    return run, content, v1



def test_1_concurrent_publication_attempts():
    """
    TEST 1: Two concurrent publication attempts for the same content_version + platform
    result in only one logical publication.
    """
    print("\n--- TEST 1: Concurrent Publication Attempts ---")
    db: Session = SessionLocal()
    run, content, v1 = seed_test_workflow_tree(db)
    db.close()

    results = []
    errors = []

    def attempt_publish():
        worker_db: Session = SessionLocal()
        try:
            provider = LocalTestPublisher()
            svc = PublishingService(provider=provider)
            pub = svc.publish_content_version(
                db=worker_db,
                workflow_run_id=run.id,
                content_version_id=v1.id,
                platform="linkedin",
            )
            results.append(pub.id)
        except Exception as e:
            errors.append(e)
        finally:
            worker_db.close()

    # Run two concurrent threads
    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_publish)
        f2 = executor.submit(attempt_publish)
        f1.result()
        f2.result()

    verify_db: Session = SessionLocal()
    key = build_idempotency_key(v1.id, "linkedin")
    pubs = verify_db.query(Publication).filter(Publication.idempotency_key == key).all()
    analytics_count = (
        verify_db.query(Analytics)
        .filter(Analytics.publication_id == pubs[0].id)
        .count()
    ) if pubs else 0
    verify_db.close()

    assert len(pubs) == 1, f"Expected exactly 1 publication row in DB, got {len(pubs)}"
    assert len(results) == 2, f"Both callers should receive the publication record, got {len(results)}"
    assert results[0] == results[1], f"Both callers should receive identical publication ID: {results}"
    assert analytics_count == 1, f"Expected exactly 1 initial analytics snapshot row, got {analytics_count}"
    print(f"✓ TEST 1 PASSED: Exactly 1 publication created ({pubs[0].id}) and exactly 1 initial analytics snapshot despite 2 concurrent threads.")



def test_2_repeated_publication_request():
    """
    TEST 2: Repeated publication request with same idempotency key does not create another publication.
    """
    print("\n--- TEST 2: Repeated Publication Request ---")
    db: Session = SessionLocal()
    run, content, v1 = seed_test_workflow_tree(db)
    svc = PublishingService(provider=LocalTestPublisher())

    pub1 = svc.publish_content_version(db, run.id, v1.id, platform="linkedin")
    pub2 = svc.publish_content_version(db, run.id, v1.id, platform="linkedin")

    key = build_idempotency_key(v1.id, "linkedin")
    total_rows = db.query(Publication).filter(Publication.idempotency_key == key).count()
    db.close()

    assert pub1.id == pub2.id, f"IDs mismatch: {pub1.id} != {pub2.id}"
    assert total_rows == 1, f"Expected 1 DB row, found {total_rows}"
    print(f"✓ TEST 2 PASSED: Repeated call returned identical publication {pub1.id}, no duplicate rows.")


def test_3_already_published_returns_existing_external_id():
    """
    TEST 3: Already PUBLISHED publication returns existing external_post_id.
    """
    print("\n--- TEST 3: Already Published Returns Existing External ID ---")
    db: Session = SessionLocal()
    run, content, v1 = seed_test_workflow_tree(db)
    svc = PublishingService(provider=LocalTestPublisher())

    pub1 = svc.publish_content_version(db, run.id, v1.id, platform="linkedin")
    orig_ext_id = pub1.external_id
    assert orig_ext_id is not None, "external_id should be populated"

    pub2 = svc.publish_content_version(db, run.id, v1.id, platform="linkedin")
    assert pub2.external_id == orig_ext_id, f"external_id changed: {pub2.external_id} vs {orig_ext_id}"
    db.close()
    print(f"✓ TEST 3 PASSED: Returned existing external_post_id '{orig_ext_id}'.")


def test_4_transient_failure_can_be_retried():
    """
    TEST 4: A transient failure can be retried and succeeds within retry bounds.
    """
    print("\n--- TEST 4: Transient Failure Retry ---")
    db: Session = SessionLocal()
    run, content, v1 = seed_test_workflow_tree(db)

    # Provider simulates 2 transient failures, then succeeds on attempt 3
    test_provider = LocalTestPublisher(simulate_transient_failure_count=2)
    svc = PublishingService(provider=test_provider)

    pub = svc.publish_content_version(
        db,
        run.id,
        v1.id,
        platform="linkedin",
        max_transient_retries=3,
    )

    assert pub.status == PublicationStatus.PUBLISHED, f"Expected PUBLISHED, got {pub.status}"
    assert pub.publication_metadata.get("attempts") == 3, f"Expected 3 attempts, got {pub.publication_metadata.get('attempts')}"
    db.close()
    print(f"✓ TEST 4 PASSED: Transient failure recovered on attempt 3 and marked PUBLISHED.")


def test_5_permanent_failure_does_not_retry_forever():
    """
    TEST 5: A permanent failure does not retry forever; transitions to FAILED immediately.
    """
    print("\n--- TEST 5: Permanent Failure Halts Immediately ---")
    db: Session = SessionLocal()
    run, content, v1 = seed_test_workflow_tree(db)

    test_provider = LocalTestPublisher(simulate_permanent_failure=True)
    svc = PublishingService(provider=test_provider)

    failed = False
    try:
        svc.publish_content_version(
            db,
            run.id,
            v1.id,
            platform="linkedin",
            max_transient_retries=5,
        )
    except PermanentPublishingError:
        failed = True

    assert failed, "Expected PermanentPublishingError to be raised"
    key = build_idempotency_key(v1.id, "linkedin")
    pub = db.query(Publication).filter(Publication.idempotency_key == key).first()
    assert pub.status == PublicationStatus.FAILED, f"Expected status FAILED, got {pub.status}"
    assert pub.publication_metadata.get("attempts") == 1, f"Permanent error should stop after 1 attempt, took {pub.publication_metadata.get('attempts')}"
    assert "PermanentPublishingError" in (pub.error or ""), f"Expected error details in DB, got {pub.error}"
    db.close()
    print(f"✓ TEST 5 PASSED: Permanent failure halted after 1 attempt and recorded FAILED.")


def test_6_rejected_workflow_cannot_publish():
    """
    TEST 6: A rejected workflow cannot publish.
    """
    print("\n--- TEST 6: Rejected Workflow Cannot Publish ---")
    db: Session = SessionLocal()
    # Seed a workflow with REJECTED status
    run, content, v1 = seed_test_workflow_tree(db, run_status=WorkflowRunStatus.REJECTED, approved=False)
    # Record REJECTED approval
    approval = Approval(
        id=uuid4(),
        content_version_id=v1.id,
        status=ApprovalStatus.REJECTED,
        feedback="Tone is completely off.",
    )
    db.add(approval)
    db.commit()

    svc = PublishingService(provider=LocalTestPublisher())
    rejected_caught = False
    try:
        svc.publish_content_version(db, run.id, v1.id, platform="linkedin")
    except ValueError as e:
        rejected_caught = True
        print(f"  Rejected check caught as expected: {e}")

    assert rejected_caught, "Expected ValueError preventing publishing of rejected workflow/version"
    key = build_idempotency_key(v1.id, "linkedin")
    assert db.query(Publication).filter(Publication.idempotency_key == key).count() == 0
    db.close()
    print("✓ TEST 6 PASSED: Rejected workflow draft rejected from publishing.")


def test_7_stale_content_version_cannot_publish():
    """
    TEST 7: A stale content version cannot publish if a newer version has replaced it.
    """
    print("\n--- TEST 7: Stale Content Version Cannot Publish ---")
    db: Session = SessionLocal()
    run, content, v1 = seed_test_workflow_tree(db)

    # Add v2 (revision)
    v2 = ContentVersion(
        id=uuid4(),
        content_id=content.id,
        version_number=2,
        origin=ContentVersionOrigin.WRITER_AGENT,
        title="Test Post Title v2",
        body="Revised body for v2.",
    )
    db.add(v2)
    # Approve v2
    approval_v2 = Approval(
        id=uuid4(),
        content_version_id=v2.id,
        status=ApprovalStatus.APPROVED,
        feedback="v2 looks great!",
    )
    db.add(approval_v2)
    db.commit()

    svc = PublishingService(provider=LocalTestPublisher())

    # Try publishing stale v1
    stale_caught = False
    try:
        svc.publish_content_version(db, run.id, v1.id, platform="linkedin")
    except ValueError as e:
        stale_caught = True
        print(f"  Stale version check caught: {e}")

    assert stale_caught, "Expected publishing stale version v1 to fail"
    db.close()
    print("✓ TEST 7 PASSED: Stale content version v1 was refused.")


def test_8_newer_approved_version_publishes_correctly():
    """
    TEST 8: A newer approved version does not cause an older version to publish accidentally.
    """
    print("\n--- TEST 8: Newer Approved Version Publishes Correctly ---")
    db: Session = SessionLocal()
    run, content, v1 = seed_test_workflow_tree(db)

    # Create v2
    v2 = ContentVersion(
        id=uuid4(),
        content_id=content.id,
        version_number=2,
        origin=ContentVersionOrigin.WRITER_AGENT,
        title="Title v2",
        body="Body v2.",
    )
    db.add(v2)
    appr_v2 = Approval(
        id=uuid4(),
        content_version_id=v2.id,
        status=ApprovalStatus.APPROVED,
        feedback="Approved v2",
    )
    db.add(appr_v2)
    db.commit()

    svc = PublishingService(provider=LocalTestPublisher())
    pub_v2 = svc.publish_content_version(db, run.id, v2.id, platform="linkedin")

    assert pub_v2.content_version_id == v2.id, "Publication should reference v2"
    assert pub_v2.status == PublicationStatus.PUBLISHED
    key_v1 = build_idempotency_key(v1.id, "linkedin")
    assert db.query(Publication).filter(Publication.idempotency_key == key_v1).count() == 0
    db.close()
    print("✓ TEST 8 PASSED: Only current approved v2 was published, v1 left untouched.")


def test_9_successful_publication_persists_provenance():
    """
    TEST 9: Successful publication persists external_post_id, published_at, status.
    """
    print("\n--- TEST 9: Provenance Persistence ---")
    db: Session = SessionLocal()
    run, content, v1 = seed_test_workflow_tree(db)
    svc = PublishingService(provider=LocalTestPublisher())

    pub = svc.publish_content_version(db, run.id, v1.id, platform="linkedin")
    assert pub.external_id is not None and pub.external_id.startswith("linkedin_")
    assert pub.published_at is not None
    assert pub.status == PublicationStatus.PUBLISHED
    assert pub.url is not None
    db.close()
    print(f"✓ TEST 9 PASSED: Provenance persisted (external_id={pub.external_id}, published_at={pub.published_at}).")


def test_10_publication_failure_persists_useful_error_information():
    """
    TEST 10: Publication failure persists useful error information.
    """
    print("\n--- TEST 10: Failure Error Persistence ---")
    db: Session = SessionLocal()
    run, content, v1 = seed_test_workflow_tree(db)

    test_provider = LocalTestPublisher(simulate_timeout=True)
    svc = PublishingService(provider=test_provider)

    try:
        svc.publish_content_version(db, run.id, v1.id, platform="linkedin")
    except AmbiguousTimeoutPublishingError:
        pass

    key = build_idempotency_key(v1.id, "linkedin")
    pub = db.query(Publication).filter(Publication.idempotency_key == key).first()
    assert pub.status == PublicationStatus.FAILED
    assert "AmbiguousTimeoutPublishingError" in pub.error
    assert "timeout" in pub.error.lower()
    db.close()
    print(f"✓ TEST 10 PASSED: Error details properly recorded: {pub.error}")


def main():
    print("=" * 60)
    print("RUNNING PHASE 11 PUBLISHING ATOMICITY & CONCURRENCY SUITE")
    print("=" * 60)
    tests = [
        test_1_concurrent_publication_attempts,
        test_2_repeated_publication_request,
        test_3_already_published_returns_existing_external_id,
        test_4_transient_failure_can_be_retried,
        test_5_permanent_failure_does_not_retry_forever,
        test_6_rejected_workflow_cannot_publish,
        test_7_stale_content_version_cannot_publish,
        test_8_newer_approved_version_publishes_correctly,
        test_9_successful_publication_persists_provenance,
        test_10_publication_failure_persists_useful_error_information,
    ]

    for t in tests:
        t()

    print("\n" + "=" * 60)
    print("ALL 10 PUBLISHING CONCURRENCY & IDEMPOTENCY TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    main()
