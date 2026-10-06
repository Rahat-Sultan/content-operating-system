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


class NetworkAnalyticsError(TransientAnalyticsError):
    """
    This server could not reach the provider (DNS failure, refused or reset
    connection, timeout). Says nothing about whether the provider has metrics,
    so it must never be reported as "not yet collected" or counted as an
    attempt on the metrics retry ladder.
    """
    pass


class PermanentAnalyticsError(AnalyticsError):
    """Terminal failure (e.g. bad credentials, post deleted/invalid); do not retry."""
    def __init__(self, message: str):
        super().__init__(message, is_transient=False)


class PostNotFoundError(PermanentAnalyticsError):
    """Post does not exist on provider (permanent 404)."""
    def __init__(self, message: str = "Post not found on analytics provider."):
        super().__init__(message)


class MetricsNotAvailableError(AnalyticsError):
    """
    Post metrics are not yet available from the provider (e.g. downstream platform
    processing or Buffer analytics indexing delay for newly published posts).
    Retryable after a short delay.
    """
    def __init__(self, message: str = "Metrics are not yet available from the provider. Please try again shortly."):
        super().__init__(message, is_transient=True)


class MetricsUnsupportedError(AnalyticsError):
    """
    Provider does not support analytics for this channel type or post.
    Non-retryable by scheduler.
    """
    def __init__(self, message: str = "Analytics are not supported for this channel type by the provider."):
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
