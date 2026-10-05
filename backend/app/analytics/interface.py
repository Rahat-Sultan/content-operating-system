from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


class AnalyticsError(Exception):
    """Base exception for analytics operations."""
    def __init__(self, message: str, is_transient: bool = False):
        super().__init__(message)
        self.is_transient = is_transient


class TransientAnalyticsError(AnalyticsError):
    """Temporary failure (e.g. rate limit, 503, network glitch); safe to retry."""
    def __init__(self, message: str):
        super().__init__(message, is_transient=True)


class PermanentAnalyticsError(AnalyticsError):
    """Terminal failure (e.g. bad credentials, post not found); do not retry."""
    def __init__(self, message: str):
        super().__init__(message, is_transient=False)


@dataclass
class AnalyticsRequest:
    publication_id: UUID
    platform: str
    external_post_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalyticsResult:
    publication_id: UUID
    platform: str
    external_post_id: str
    metrics: dict[str, Any]
    collected_at: datetime
    provider: str
    is_stub: bool = False


class AnalyticsProvider(ABC):
    """
    Abstract interface for analytics providers.
    Follows the same pattern as PublisherInterface.
    """

    @abstractmethod
    def fetch_metrics(self, request: AnalyticsRequest) -> AnalyticsResult:
        """
        Fetches performance metrics for a published post.
        """
        pass
