"""
Blocks server-side request forgery through source URLs. A source's feed URL is typed
by the logged-in user and later fetched by the worker with no further confirmation, so
an unchecked URL would let an account make the server issue HTTP requests to internal
services, cloud metadata endpoints, or the filesystem (feedparser also accepts
file:// and ftp://). Checked at save time (fast feedback) and again right before every
fetch (defense in depth, in case a URL ever reaches storage some other way).

This does not pin the resolved IP for the request itself, so a DNS-rebinding attacker
who controls both the DNS answer and the fetch's exact timing could still slip a
private address past this check. That is a narrower, more sophisticated attack than
the direct "type an internal URL" case this closes, and out of scope for this pass.
"""
import ipaddress
import socket
from urllib.parse import urlparse

from fastapi import HTTPException, status

ALLOWED_SCHEMES = {"http", "https"}


def _is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def assert_safe_feed_url(url: str) -> None:
    """Raises HTTPException(422) if the URL is not a safe public http(s) feed address."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Source links must start with http:// or https://.",
        )
    host = parsed.hostname
    if not host:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That link has no host.")
    if host.lower() in ("localhost", "metadata.google.internal"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That host is not allowed.")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="That host could not be resolved.")

    for info in infos:
        ip = info[4][0]
        try:
            if _is_blocked_ip(ip):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="That link resolves to a private or internal address, which is not allowed.",
                )
        except ValueError:
            continue
