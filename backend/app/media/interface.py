from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID
from typing import Any


class ImageGenerationError(Exception):
    """Base exception for image generation errors."""
    pass


class TransientImageGenerationError(ImageGenerationError):
    """Temporary failure (e.g. rate limit, connection timeout, upstream 503). Retrying is allowed."""
    pass


class PermanentImageGenerationError(ImageGenerationError):
    """Fatal failure (e.g. invalid request, authentication error, policy rejection). Do not retry blindly."""
    pass


@dataclass
class ImageGenerationRequest:
    content_version_id: UUID
    prompt: str
    title: str | None = None
    topic: str | None = None
    width: int = 1200
    height: int = 630


@dataclass
class ImageGenerationResult:
    provider: str
    provider_asset_id: str | None
    mime_type: str
    width: int
    height: int
    data: bytes  # Binary payload delivered to storage boundary
    alt_text: str | None
    metadata: dict[str, Any] = field(default_factory=dict)
    is_stub: bool = False


class ImageGenerationProvider(ABC):
    """
    Abstract interface for image generation providers.
    Follows PublisherInterface and AnalyticsProvider patterns.
    """

    @abstractmethod
    def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """
        Generate an image matching the request.
        Raises TransientImageGenerationError or PermanentImageGenerationError.
        """
        pass
