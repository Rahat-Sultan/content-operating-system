"""
Suggested RSS sources for this niche (chip design, hardware security, AI supply chain).

Sources marked default=True are added to every new account at registration. The rest
are offered on the Sources page to add by hand. Every entry is a feed URL that sync can
read with feedparser; no scraping.
"""
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.sources.models import Source

SUGGESTED_SOURCES: list[dict[str, Any]] = [
    {"name": "Hacker News", "url": "https://news.ycombinator.com/rss", "topic": "Tech news", "default": True},
    {"name": "arXiv cs.CR (Cryptography and Security)", "url": "http://export.arxiv.org/rss/cs.CR", "topic": "Research", "default": True},
    {"name": "arXiv cs.AR (Hardware Architecture)", "url": "http://export.arxiv.org/rss/cs.AR", "topic": "Research", "default": True},
    {"name": "Semiconductor Engineering", "url": "https://semiengineering.com/feed/", "topic": "Chip design", "default": True},
    {"name": "The Hacker News", "url": "https://feeds.feedburner.com/TheHackersNews", "topic": "Security news", "default": True},
    {"name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/", "topic": "AI", "default": True},
    {"name": "Krebs on Security", "url": "https://krebsonsecurity.com/feed/", "topic": "Security news", "default": False},
    {"name": "BleepingComputer", "url": "https://www.bleepingcomputer.com/feed/", "topic": "Security news", "default": False},
    {"name": "The Register: Security", "url": "https://www.theregister.com/security/headlines.atom", "topic": "Security news", "default": False},
]


def seed_default_sources(db: Session, owner_id) -> int:
    """Adds the default sources for one account. Called once, at registration."""
    added = 0
    for entry in SUGGESTED_SOURCES:
        if not entry["default"]:
            continue
        db.add(Source(
            id=uuid4(),
            owner_id=owner_id,
            name=entry["name"],
            source_type="rss",
            url=entry["url"],
            enabled=True,
            config={"topic": entry["topic"]},
        ))
        added += 1
    db.commit()
    return added


def suggestions_for(db: Session, owner_id) -> list[dict[str, Any]]:
    """Suggested sources this account does not have yet, matched by feed URL."""
    have = {url for (url,) in db.query(Source.url).filter(Source.owner_id == owner_id).all()}
    return [
        {"name": e["name"], "url": e["url"], "topic": e["topic"]}
        for e in SUGGESTED_SOURCES
        if e["url"] not in have
    ]
