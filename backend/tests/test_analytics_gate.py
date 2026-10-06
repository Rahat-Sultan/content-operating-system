"""
Gate and network classification for the Buffer analytics provider.
No database and no network: HTTP is replaced by real fixtures or by httpx errors.

Fixtures (real responses, 2026-10-06):
  buffer_post_collected_6ac3541.json    Impressions/Reach present: Buffer collected data
  buffer_post_placeholder_6abf5652.json Reactions/Comments only at zero, metricsUpdatedAt > sentAt
"""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

import httpx

from app.analytics.buffer_provider import BufferAnalyticsProvider
from app.analytics.interface import (
    AnalyticsRequest,
    MetricsNotAvailableError,
    NetworkAnalyticsError,
    TransientAnalyticsError,
)
from uuid import uuid4

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name: str) -> dict:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


def _request(post_id: str = "6ac3541363761da98b71e85b") -> AnalyticsRequest:
    return AnalyticsRequest(publication_id=uuid4(), platform="linkedin", external_post_id=post_id)


class TestBufferMetricsGate(unittest.TestCase):
    def _fetch(self, payload: dict):
        provider = BufferAnalyticsProvider(access_token="test-token")
        with patch("app.analytics.buffer_provider.httpx.Client") as client_cls:
            response = MagicMock(status_code=200, text="")
            response.json.return_value = payload
            client_cls.return_value.__enter__.return_value.post.return_value = response
            return provider.fetch_metrics(_request())

    def test_collected_response_is_stored_with_real_values(self):
        result = self._fetch(_load("buffer_post_collected_6ac3541.json"))
        self.assertEqual(result.metrics["impressions"], 95)
        self.assertEqual(result.metrics["reactions"], 2)
        self.assertEqual(result.metrics["is_stub"], False)
        self.assertEqual(result.provider, "buffer")

    def test_placeholder_is_rejected_even_though_metrics_updated_after_sent(self):
        # This fixture has metricsUpdatedAt > sentAt. A timestamp gate would accept it
        # and store zeros as real data. The metric shape is what must reject it.
        payload = _load("buffer_post_placeholder_6abf5652.json")
        post = payload["data"]["post"]
        self.assertGreater(post["metricsUpdatedAt"], post["sentAt"])
        with self.assertRaises(MetricsNotAvailableError):
            self._fetch(payload)

    def test_empty_metrics_list_is_not_stored(self):
        payload = _load("buffer_post_collected_6ac3541.json")
        payload["data"]["post"]["metrics"] = []
        with self.assertRaises(MetricsNotAvailableError):
            self._fetch(payload)

    def test_collected_zeros_are_stored(self):
        # A quiet post that Buffer did measure: impressions is present with 0.
        payload = _load("buffer_post_collected_6ac3541.json")
        for metric in payload["data"]["post"]["metrics"]:
            metric["value"] = 0
        result = self._fetch(payload)
        self.assertEqual(result.metrics["impressions"], 0)
        self.assertEqual(result.metrics["reactions"], 0)

    def test_missing_metrics_updated_at_is_not_stored(self):
        payload = _load("buffer_post_collected_6ac3541.json")
        payload["data"]["post"]["metricsUpdatedAt"] = None
        with self.assertRaises(MetricsNotAvailableError):
            self._fetch(payload)


class TestBufferNetworkClassification(unittest.TestCase):
    """Simulated transport failures. Each must surface as NetworkAnalyticsError, never as a metrics answer."""

    def _fetch_raising(self, exc: Exception):
        provider = BufferAnalyticsProvider(access_token="test-token")
        with patch("app.analytics.buffer_provider.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.post.side_effect = exc
            return provider.fetch_metrics(_request())

    def test_dns_failure(self):
        # The production message: [Errno -3] Temporary failure in name resolution
        exc = httpx.ConnectError("[Errno -3] Temporary failure in name resolution")
        with self.assertRaises(NetworkAnalyticsError) as ctx:
            self._fetch_raising(exc)
        self.assertTrue(ctx.exception.is_transient)

    def test_timeout(self):
        with self.assertRaises(NetworkAnalyticsError):
            self._fetch_raising(httpx.ConnectTimeout("timed out"))

    def test_connection_reset(self):
        with self.assertRaises(NetworkAnalyticsError):
            self._fetch_raising(httpx.ReadError("[Errno 104] Connection reset by peer"))

    def test_network_error_is_a_transient_error_but_not_a_metrics_answer(self):
        self.assertTrue(issubclass(NetworkAnalyticsError, TransientAnalyticsError))
        self.assertFalse(issubclass(NetworkAnalyticsError, MetricsNotAvailableError))


if __name__ == "__main__":
    unittest.main()
