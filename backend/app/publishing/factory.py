import logging
from app.config import settings
from app.publishing.interface import PublisherInterface
from app.publishing.local_provider import LocalTestPublisher

logger = logging.getLogger(__name__)

# Singleton instance of LocalTestPublisher for predictable testing / lifecycle
_default_local_publisher = LocalTestPublisher()


def get_publisher_provider(provider_name: str | None = None) -> PublisherInterface:
    """
    Factory function returning the configured publishing provider.
    Defaults to settings.publisher_provider ('local').
    Decoupled from commercial platforms until explicit credentials & requirements exist.
    """
    selected = (provider_name or settings.publisher_provider or "local").lower()

    if selected in ("local", "test", "stub"):
        return _default_local_publisher
    
    # Ready for future providers (e.g. 'linkedin', 'buffer', etc.)
    logger.warning("Unknown publisher provider '%s', falling back to LocalTestPublisher", selected)
    return _default_local_publisher
