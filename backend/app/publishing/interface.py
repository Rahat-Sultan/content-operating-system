from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class PublishingOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"
    TIMEOUT_AMBIGUOUS = "TIMEOUT_AMBIGUOUS"


class PublishingError(Exception):
    """Base exception for publishing failures."""
    def __init__(self, message: str, is_transient: bool = False):
        super().__init__(message)
        self.is_transient = is_transient


class TransientPublishingError(PublishingError):
    """Temporary failure (e.g. rate limit, 503, network glitch); safe and appropriate to retry."""
    def __init__(self, message: str):
        super().__init__(message, is_transient=True)


class PermanentPublishingError(PublishingError):
    """Terminal failure (e.g. bad credentials, validation error, platform policy reject); do NOT retry blindly."""
    def __init__(self, message: str):
        super().__init__(message, is_transient=False)


class AmbiguousTimeoutPublishingError(PublishingError):
    """Request was sent but response timed out; outcome unknown at external provider."""
    def __init__(self, message: str):
        super().__init__(message, is_transient=False)


@dataclass
class PublishRequest:
    workflow_run_id: UUID
    content_version_id: UUID
    platform: str
    title: str | None
    body: str
    idempotency_key: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PublishResult:
    platform: str
    external_post_id: str
    url: str | None
    published_at: datetime
    provider_metadata: dict[str, Any] = field(default_factory=dict)


class PublisherInterface(ABC):
    """
    Abstract interface for publishing providers.
    Decouples Content OS business domain from external platform APIs (LinkedIn, Ayrshare, Buffer, etc.).
    """

    @abstractmethod
    def publish(self, request: PublishRequest) -> PublishResult:
        """
        Publishes content using the provided deterministic PublishRequest.
        Must respect request.idempotency_key for safe deduplication/retries.
        """
        pass
