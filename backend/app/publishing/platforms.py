"""
Platforms Content OS knows about, and whether a publishing channel is connected.

Only LinkedIn is connected (through Buffer). The others are listed so the UI can say
"not connected" honestly, and are never shown with invented numbers. Keys match
Publication.platform and the strategy's `platforms` list (lower case).
"""
from typing import TypedDict


class PlatformInfo(TypedDict):
    key: str
    label: str
    connected: bool


PLATFORMS: list[PlatformInfo] = [
    {"key": "linkedin", "label": "LinkedIn", "connected": True},
    {"key": "facebook", "label": "Facebook", "connected": False},
    {"key": "instagram", "label": "Instagram", "connected": False},
    {"key": "reddit", "label": "Reddit", "connected": False},
    {"key": "substack", "label": "Substack", "connected": False},
]

_BY_KEY = {p["key"]: p for p in PLATFORMS}


def normalize_platform(name: str) -> str:
    return (name or "").strip().lower()


def platform_label(key: str) -> str:
    info = _BY_KEY.get(normalize_platform(key))
    return info["label"] if info else key


def platforms_for_strategy_config(config: dict | None) -> list[str]:
    """The strategy's target platforms, normalized, in the order the strategy lists them."""
    raw = (config or {}).get("platforms") or []
    seen: list[str] = []
    for item in raw:
        key = normalize_platform(str(item))
        if key and key not in seen:
            seen.append(key)
    return seen
