import logging
from app.config import settings
from app.publishing.interface import PublisherInterface
from app.publishing.local_provider import LocalTestPublisher
from app.publishing.buffer_provider import BufferPublisher, is_placeholder_buffer_token

logger = logging.getLogger(__name__)

# Singleton instance of LocalTestPublisher for predictable testing / lifecycle
_default_local_publisher = LocalTestPublisher()
_default_buffer_publisher: BufferPublisher | None = None


def get_publisher_provider(provider_name: str | None = None) -> PublisherInterface:
    """
    Factory function returning the configured publishing provider.
    Defaults to settings.publisher_provider ('local').
    
    If 'buffer' is selected:
    - Verifies that BUFFER_ACCESS_TOKEN is configured and non-placeholder.
    - If valid, returns BufferPublisher.
    - If missing or placeholder, logs a loud warning and falls back to LocalTestPublisher.
    """
    selected = (provider_name or settings.publisher_provider or "local").lower()

    if selected in ("local", "test", "stub"):
        return _default_local_publisher

    if selected == "buffer":
        token = settings.buffer_access_token
        if is_placeholder_buffer_token(token):
            logger.warning(
                "\n"
                "====================================================================\n"
                "⚠️  WARNING: PUBLISHER_PROVIDER is set to 'buffer' but BUFFER_ACCESS_TOKEN\n"
                "   is missing or placeholder! Falling back to LocalTestPublisher.\n"
                "   Set a valid BUFFER_ACCESS_TOKEN in backend/.env to publish via Buffer.\n"
                "====================================================================\n"
            )
            return _default_local_publisher

        global _default_buffer_publisher
        if _default_buffer_publisher is None:
            _default_buffer_publisher = BufferPublisher()
        return _default_buffer_publisher

    logger.warning("Unknown publisher provider '%s', falling back to LocalTestPublisher", selected)
    return _default_local_publisher
