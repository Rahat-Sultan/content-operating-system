from datetime import datetime, timezone
import hashlib
from typing import Any
import feedparser


def fetch_rss_items(feed_url: str) -> list[dict[str, Any]]:
    """
    Fetches a real RSS feed URL, parses it, and returns normalized items.
    Deterministic ingestion — no LLM involved.
    
    Returns a list of dicts:
      - title: str
      - url: str
      - author: str | None
      - published_at: str | None
      - description: str | None
      - external_id: str
      - content_hash: str
    """
    feed = feedparser.parse(feed_url)
    items: list[dict[str, Any]] = []

    for entry in feed.entries:
        title = entry.get("title") or "Untitled"
        url = entry.get("link") or ""
        external_id = entry.get("id") or url or title
        author = entry.get("author")
        
        # Published timestamp normalization
        published_at = entry.get("published") or entry.get("updated")
        
        # Summary / content
        description = entry.get("summary") or entry.get("description") or ""

        # Content hash fallback
        hash_content = f"{title}|{url}|{description}"
        content_hash = hashlib.sha256(hash_content.encode("utf-8")).hexdigest()

        items.append({
            "title": title,
            "url": url,
            "author": author,
            "published_at": published_at,
            "description": description,
            "external_id": str(external_id),
            "content_hash": content_hash,
            "raw_entry": {
                "tags": [t.get("term") for t in entry.get("tags", []) if t.get("term")],
            }
        })

    return items
