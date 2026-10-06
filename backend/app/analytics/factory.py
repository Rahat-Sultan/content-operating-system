import logging
from app.config import settings
from app.accounts.context import active_key
from app.analytics.interface import AnalyticsProvider
from app.analytics.local_provider import LocalTestAnalyticsProvider
from app.analytics.buffer_provider import BufferAnalyticsProvider
from app.publishing.buffer_provider import is_placeholder_buffer_token

logger = logging.getLogger(__name__)

_default_local_analytics = LocalTestAnalyticsProvider()


def get_analytics_provider(provider_name: str | None = None) -> AnalyticsProvider:
    """
    Factory function returning the configured analytics provider.
    Defaults to settings.publisher_provider (e.g. 'buffer' or 'local').

    If 'buffer' is selected:
    - Verifies that BUFFER_ACCESS_TOKEN is configured and non-placeholder.
    - If valid, returns BufferAnalyticsProvider.
    - If missing or placeholder, logs loud warning and falls back to LocalTestAnalyticsProvider with is_stub: true.
    """
    selected = (provider_name or settings.publisher_provider or "local").lower()

    if selected in ("local", "test", "stub"):
        return _default_local_analytics

    if selected == "buffer":
        token = active_key("BUFFER_ACCESS_TOKEN")
        if is_placeholder_buffer_token(token):
            logger.warning(
                "\n"
                "====================================================================\n"
                "⚠️  WARNING: Analytics provider is set to 'buffer' but BUFFER_ACCESS_TOKEN\n"
                "   is missing or placeholder! Falling back to LocalTestAnalyticsProvider.\n"
                "====================================================================\n"
            )
            return _default_local_analytics

        return BufferAnalyticsProvider()  # per call: each account's token is read when the provider is built

    logger.warning("Unknown analytics provider '%s', falling back to LocalTestAnalyticsProvider", selected)
    return _default_local_analytics
