from datetime import datetime, timezone
from typing import Any
import uuid


def execute_publish(
    content_version_id: uuid.UUID,
    title: str | None,
    body: str,
    platform: str = "linkedin",
) -> dict[str, Any]:
    """
    Minimal publishing provider stub simulating posting to social/blog platforms.
    Isolates external platform API calls behind this interface.
    Returns fake but realistic platform responses marked with is_stub: True.
    """
    fake_post_id = f"{platform}_{uuid.uuid4().hex[:12]}"
    fake_url = f"https://www.{platform}.com/posts/{fake_post_id}"

    return {
        "is_stub": True,
        "platform": platform,
        "external_post_id": fake_post_id,
        "url": fake_url,
        "published_at": datetime.now(timezone.utc).isoformat(),
        "platform_response": {
            "status": "success",
            "characters_posted": len(body),
            "media_attached": False,
        }
    }
