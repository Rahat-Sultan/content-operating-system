"""
Read-only diagnostic: what does Buffer return for every real published post?

Usage (run from backend/, in your own terminal, with network access):

    python -m app.analytics.diagnose               # print the table
    python -m app.analytics.diagnose --save-raw DIR  # also write raw JSON per post

Only sends `post(input: {id})` queries. Never calls createPost. Never writes
to the database. Never prints the access token.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.db import SessionLocal
from app.publishing.models import Publication, PublicationStatus
from app.analytics.buffer_provider import BufferAnalyticsProvider, build_post_metrics_query
from app.analytics.interface import (
    NetworkAnalyticsError,
    PermanentAnalyticsError,
    TransientAnalyticsError,
)

# external_id prefixes written by the local test provider. Not Buffer posts.
LOCAL_PROVIDER_PREFIXES = ("linkedin_", "test-ext-", "stub_")

SECRET_KEYS = ("authorization", "token", "secret", "password", "api_key")


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: ("[REDACTED]" if any(s in k.lower() for s in SECRET_KEYS) else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def classify(post: dict | None, errors: list | None) -> dict[str, Any]:
    """
    Turns one raw Buffer response into a label plus the numbers the report needs.
    Labels: no_post, graphql_error, no_metrics, no_metrics_updated_at,
    placeholder (metricsUpdatedAt <= sentAt), collected (metricsUpdatedAt > sentAt).
    """
    out: dict[str, Any] = {
        "buffer_status": None,
        "sent_at": None,
        "metrics_updated_at": None,
        "mua_minus_sent_s": None,
        "metrics_len": 0,
        "nonzero_metrics": 0,
        "label": None,
    }
    if errors:
        out["label"] = f"graphql_error: {errors[0].get('message', '')[:80]}"
        return out
    if not post:
        out["label"] = "no_post"
        return out

    sent = _parse_ts(post.get("sentAt"))
    mua = _parse_ts(post.get("metricsUpdatedAt"))
    metrics = post.get("metrics") or []
    out.update(
        buffer_status=post.get("status"),
        sent_at=post.get("sentAt"),
        metrics_updated_at=post.get("metricsUpdatedAt"),
        metrics_len=len(metrics),
        nonzero_metrics=sum(1 for m in metrics if (m.get("value") or 0) != 0),
    )
    if sent and mua:
        out["mua_minus_sent_s"] = round((mua - sent).total_seconds(), 3)

    if not metrics:
        out["label"] = "no_metrics"
    elif mua is None:
        out["label"] = "no_metrics_updated_at"
    elif sent is not None and mua <= sent:
        out["label"] = "placeholder"
    else:
        out["label"] = "collected"
    return out


def _query_one(provider: BufferAnalyticsProvider, post_id: str) -> tuple[dict | None, list | None, str | None]:
    """Returns (post, graphql_errors, transport_error). Never raises."""
    try:
        data = provider._execute_graphql(build_post_metrics_query(post_id))
    except NetworkAnalyticsError as err:
        return None, None, f"network_error: {err}"
    except (TransientAnalyticsError, PermanentAnalyticsError) as err:
        return None, None, f"http_error: {err}"
    return (data.get("data") or {}).get("post"), data.get("errors"), None


def run_diagnostic(save_raw_dir: Path | None = None) -> list[dict[str, Any]]:
    provider = BufferAnalyticsProvider()
    if not provider.access_token:
        print("BUFFER_ACCESS_TOKEN is not configured in backend/.env (or is empty). Nothing queried.")
        return []

    db = SessionLocal()
    try:
        pubs = (
            db.query(Publication)
            .filter(
                Publication.status == PublicationStatus.PUBLISHED,
                Publication.external_id.isnot(None),
            )
            .order_by(Publication.published_at.asc().nulls_last())
            .all()
        )
        targets = [
            (p.id, p.external_id.strip(), p.published_at)
            for p in pubs
            if p.external_id and not p.external_id.strip().startswith(LOCAL_PROVIDER_PREFIXES)
        ]
        local_skipped = len(pubs) - len(targets)
    finally:
        db.close()

    if save_raw_dir:
        save_raw_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for pub_id, post_id, published_at in targets:
        post, errors, transport_error = _query_one(provider, post_id)
        row: dict[str, Any] = {
            "publication_id": str(pub_id),
            "post_id": post_id,
            "published_at_local": published_at.isoformat() if published_at else None,
            "age_hours": round((now - published_at).total_seconds() / 3600, 1) if published_at else None,
            "queried_at": now.isoformat(),
        }
        if transport_error:
            row.update(classify(None, None), label=transport_error)
        else:
            row.update(classify(post, errors))

        if save_raw_dir:
            raw = {"data": {"post": post}, "errors": errors}
            (save_raw_dir / f"{post_id}.json").write_text(json.dumps(_redact(raw), indent=2))
        rows.append(row)

    print(f"Queried {len(rows)} Buffer post(s). Skipped {local_skipped} local-test publication(s) (not Buffer posts).")
    print(f"Checked at {now.isoformat(timespec='seconds')}")
    print()
    header = f"{'post_id':<26} {'age_h':>6} {'buf_status':<10} {'metrics':>7} {'nonzero':>7} {'mua-sent(s)':>12}  label"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(
            f"{r['post_id']:<26} {str(r['age_hours']):>6} {str(r['buffer_status']):<10} "
            f"{r['metrics_len']:>7} {r['nonzero_metrics']:>7} {str(r['mua_minus_sent_s']):>12}  {r['label']}"
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Buffer analytics diagnostic")
    parser.add_argument("--save-raw", type=Path, default=None, help="directory to write redacted raw JSON per post")
    args = parser.parse_args(argv)
    run_diagnostic(save_raw_dir=args.save_raw)
    return 0


if __name__ == "__main__":
    sys.exit(main())
