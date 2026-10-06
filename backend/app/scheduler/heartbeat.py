from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.scheduler.models import WorkerHeartbeat

# A worker whose last heartbeat is older than this is treated as not running.
HEARTBEAT_STALE_AFTER = timedelta(minutes=2)


def write_heartbeat(db: Session, worker_id: str) -> None:
    """Records that this worker is alive now. Upserts its own row."""
    now = datetime.now(timezone.utc)
    stmt = pg_insert(WorkerHeartbeat).values(worker_id=worker_id, last_seen_at=now)
    stmt = stmt.on_conflict_do_update(
        index_elements=[WorkerHeartbeat.worker_id],
        set_={"last_seen_at": now},
    )
    db.execute(stmt)
    db.commit()


def scheduler_running(db: Session, now: datetime | None = None) -> bool:
    """True when at least one worker has a heartbeat fresher than HEARTBEAT_STALE_AFTER."""
    now = now or datetime.now(timezone.utc)
    latest = db.query(WorkerHeartbeat.last_seen_at).order_by(WorkerHeartbeat.last_seen_at.desc()).first()
    if latest is None:
        return False
    last_seen = latest[0]
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return (now - last_seen) <= HEARTBEAT_STALE_AFTER
