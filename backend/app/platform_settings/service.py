"""
Platform settings: which platforms the user has set up, and whether each is ready.

A platform is READY only when it is enabled, has a channel ID, and (for Buffer
platforms) a real Buffer token is configured in .env. Tokens are never read into,
returned by, or stored by this module beyond the presence check.
"""
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.platform_settings.models import PlatformSetting
from app.publishing.buffer_provider import BUFFER_GRAPHQL_ENDPOINT, is_placeholder_buffer_token
from app.publishing.platforms import PLATFORMS

# Buffer channel IDs are short alphanumeric strings. Anything else is refused before it
# reaches a GraphQL query.
CHANNEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

# Which platforms publish through Buffer. Others have no provider yet.
BUFFER_PLATFORMS = {"linkedin"}


def _buffer_token_configured() -> bool:
    return not is_placeholder_buffer_token(settings.buffer_access_token)


def _row(db: Session, key: str) -> PlatformSetting | None:
    return db.query(PlatformSetting).filter(PlatformSetting.key == key).first()


def platform_views(db: Session) -> list[dict[str, Any]]:
    """Every known platform with its saved settings and readiness."""
    rows = {r.key: r for r in db.query(PlatformSetting).all()}
    token_ok = _buffer_token_configured()
    out = []
    for p in PLATFORMS:
        row = rows.get(p["key"])
        enabled = bool(row and row.enabled)
        channel_id = row.channel_id if row else None
        via_buffer = p["key"] in BUFFER_PLATFORMS
        if not via_buffer:
            state, reason = "no_provider", "Publishing to this platform is not built yet."
        elif not token_ok:
            state, reason = "needs_token", "Add a Buffer access token to backend/.env, then restart the backend."
        elif not enabled:
            state, reason = "disabled", "Turned off. Turn it on and save to use it."
        elif not channel_id:
            state, reason = "needs_channel", "Enter the Buffer channel ID for this platform, then save."
        else:
            state, reason = "ready", "Enabled, channel set, token configured."
        out.append({
            "key": p["key"],
            "label": p["label"],
            "display_name": (row.display_name if row and row.display_name else p["label"]),
            "enabled": enabled,
            "channel_id": channel_id,
            "notes": row.notes if row else None,
            "publishes_via": "buffer" if via_buffer else None,
            "state": state,
            "ready": state == "ready",
            "reason": reason,
            "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
        })
    return out


def update_platform(db: Session, key: str, data: dict[str, Any]) -> dict[str, Any]:
    if key not in {p["key"] for p in PLATFORMS}:
        raise HTTPException(status_code=404, detail=f"Unknown platform '{key}'.")
    channel_id = (data.get("channel_id") or "").strip() or None
    if channel_id and not CHANNEL_ID_PATTERN.match(channel_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Channel ID may contain only letters, digits, '-' and '_' (max 64).",
        )
    row = _row(db, key)
    if row is None:
        row = PlatformSetting(key=key)
        db.add(row)
    row.enabled = bool(data.get("enabled", False))
    row.display_name = (data.get("display_name") or "").strip() or None
    row.channel_id = channel_id
    row.notes = (data.get("notes") or "").strip() or None
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return next(v for v in platform_views(db) if v["key"] == key)


def test_platform(db: Session, key: str) -> dict[str, Any]:
    """
    Read-only check against Buffer that the saved channel exists and is connected.
    Sends one query for the channel. Never publishes.
    """
    view = next((v for v in platform_views(db) if v["key"] == key), None)
    if view is None:
        raise HTTPException(status_code=404, detail=f"Unknown platform '{key}'.")
    if key not in BUFFER_PLATFORMS:
        return {"ok": False, "message": f"{view['label']} has no publishing provider yet, so there is nothing to test."}
    if not _buffer_token_configured():
        return {"ok": False, "message": "No Buffer token configured in .env."}
    if not view["channel_id"]:
        return {"ok": False, "message": "Save a channel ID first."}

    query = (
        '{ channel(input: {id: "%s"}) { id name service isDisconnected isQueuePaused } }'
        % view["channel_id"]
    )
    headers = {"Authorization": f"Bearer {settings.buffer_access_token.strip()}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=15) as client:
            res = client.post(BUFFER_GRAPHQL_ENDPOINT, headers=headers, json={"query": query})
    except httpx.HTTPError as exc:
        return {"ok": False, "message": f"Could not reach Buffer from this server ({type(exc).__name__})."}
    if res.status_code != 200:
        return {"ok": False, "message": f"Buffer answered HTTP {res.status_code}."}
    body = res.json()
    if body.get("errors"):
        return {"ok": False, "message": f"Buffer: {body['errors'][0].get('message', 'error')}"}
    channel = (body.get("data") or {}).get("channel")
    if not channel:
        return {"ok": False, "message": "No channel with that ID on this Buffer account."}
    if channel.get("isDisconnected"):
        return {"ok": False, "message": f"Channel '{channel.get('name')}' is disconnected in Buffer. Reconnect it there."}
    return {
        "ok": True,
        "message": f"Connected: {channel.get('name')} ({channel.get('service')})."
                   + (" Queue is paused." if channel.get("isQueuePaused") else ""),
    }
