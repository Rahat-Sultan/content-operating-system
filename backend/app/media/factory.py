from app.config import settings
from app.media.interface import ImageGenerationProvider
from app.media.local_provider import LocalTestImageGenerationProvider
from app.media.storage import MediaStorage
from app.media.local_storage import LocalFileMediaStorage

_default_storage: MediaStorage | None = None


def get_media_storage() -> MediaStorage:
    """Returns the configured media storage singleton."""
    global _default_storage
    if _default_storage is None:
        _default_storage = LocalFileMediaStorage()
    return _default_storage


def get_image_generation_provider() -> ImageGenerationProvider:
    """
    Returns configured ImageGenerationProvider instance.
    Defaults to LocalTestImageGenerationProvider in development or when no paid cloud provider is configured.
    """
    return LocalTestImageGenerationProvider()
