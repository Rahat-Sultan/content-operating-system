"""
A source's URL is typed by the account and later fetched by the worker unattended, so
it must never be able to point the server at an internal service, a cloud metadata
endpoint, or the local filesystem. Pure function tests; no database needed.
"""
import unittest

from fastapi import HTTPException

from app.sources.url_safety import assert_safe_feed_url


class SourceUrlSafetyTest(unittest.TestCase):
    def test_a_real_public_url_is_allowed(self):
        assert_safe_feed_url("https://example.com/feed")  # does not raise

    def test_non_http_scheme_is_rejected(self):
        for url in ("file:///etc/passwd", "ftp://example.com/feed", "gopher://example.com"):
            with self.subTest(url=url):
                with self.assertRaises(HTTPException) as ctx:
                    assert_safe_feed_url(url)
                self.assertEqual(ctx.exception.status_code, 422)

    def test_loopback_ip_is_rejected(self):
        with self.assertRaises(HTTPException):
            assert_safe_feed_url("http://127.0.0.1/feed")

    def test_localhost_hostname_is_rejected(self):
        with self.assertRaises(HTTPException):
            assert_safe_feed_url("http://localhost:8000/api/admin/users")

    def test_private_network_ip_is_rejected(self):
        for ip in ("10.0.0.5", "172.16.0.1", "192.168.1.1"):
            with self.subTest(ip=ip):
                with self.assertRaises(HTTPException):
                    assert_safe_feed_url(f"http://{ip}/feed")

    def test_link_local_cloud_metadata_ip_is_rejected(self):
        with self.assertRaises(HTTPException):
            assert_safe_feed_url("http://169.254.169.254/latest/meta-data/")

    def test_unresolvable_host_is_rejected(self):
        with self.assertRaises(HTTPException):
            assert_safe_feed_url("https://this-host-should-not-exist.invalid/feed")

    def test_missing_host_is_rejected(self):
        with self.assertRaises(HTTPException):
            assert_safe_feed_url("https:///no-host")


if __name__ == "__main__":
    unittest.main()
