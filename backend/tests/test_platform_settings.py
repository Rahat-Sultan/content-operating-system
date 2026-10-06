"""Platform settings: validation, readiness, and the read-only test. No network, no DB writes."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.platform_settings import service
from app.platform_settings.service import CHANNEL_ID_PATTERN, platform_views


class TestChannelIdValidation(unittest.TestCase):
    def test_accepts_buffer_style_ids(self):
        self.assertIsNotNone(CHANNEL_ID_PATTERN.match("6ab12cdEF_-9"))

    def test_refuses_anything_that_could_break_the_query(self):
        for bad in ['abc"}', "a b", "x)", "", "a" * 65]:
            with self.subTest(bad=bad):
                self.assertIsNone(CHANNEL_ID_PATTERN.match(bad))


class TestReadiness(unittest.TestCase):
    def _views(self, token_ok, row):
        db = MagicMock()
        db.query.return_value.all.return_value = [row] if row else []
        with patch.object(service, "_buffer_token_configured", return_value=token_ok):
            return {v["key"]: v for v in platform_views(db)}

    def test_no_token_means_needs_token(self):
        views = self._views(False, SimpleNamespace(key="linkedin", enabled=True, channel_id="abc", display_name=None, notes=None, updated_at=None))
        self.assertEqual(views["linkedin"]["state"], "needs_token")
        self.assertFalse(views["linkedin"]["ready"])

    def test_enabled_with_channel_and_token_is_ready(self):
        views = self._views(True, SimpleNamespace(key="linkedin", enabled=True, channel_id="abc", display_name=None, notes=None, updated_at=None))
        self.assertTrue(views["linkedin"]["ready"])

    def test_disabled_or_no_channel_is_not_ready(self):
        off = self._views(True, SimpleNamespace(key="linkedin", enabled=False, channel_id="abc", display_name=None, notes=None, updated_at=None))
        self.assertEqual(off["linkedin"]["state"], "disabled")
        nochan = self._views(True, SimpleNamespace(key="linkedin", enabled=True, channel_id=None, display_name=None, notes=None, updated_at=None))
        self.assertEqual(nochan["linkedin"]["state"], "needs_channel")

    def test_platforms_without_provider_say_so(self):
        views = self._views(True, None)
        self.assertEqual(views["facebook"]["state"], "no_provider")
        self.assertFalse(views["facebook"]["ready"])


class TestTestConnection(unittest.TestCase):
    def test_no_network_call_without_a_channel(self):
        db = MagicMock()
        with patch.object(service, "platform_views", return_value=[{"key": "linkedin", "label": "LinkedIn", "channel_id": None}]), \
             patch.object(service, "_buffer_token_configured", return_value=True), \
             patch("app.platform_settings.service.httpx.Client") as client:
            result = service.test_platform(db, "linkedin")
        self.assertFalse(result["ok"])
        client.assert_not_called()

    def test_unknown_platform_is_404(self):
        with self.assertRaises(HTTPException):
            service.update_platform(MagicMock(), "myspace", {})


if __name__ == "__main__":
    unittest.main()
