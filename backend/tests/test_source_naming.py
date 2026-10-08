"""
A source is named after what the user typed, or a short label from its link when they
typed nothing: the first part of the domain, so the Sources page shows "krebsonsecurity"
rather than the whole feed URL. Always editable afterward.
"""
import unittest

from app.sources.service import default_name_from_url, source_name_for


class TestSourceNaming(unittest.TestCase):
    def test_typed_name_wins_over_the_link(self):
        self.assertEqual(source_name_for("My feed", "https://krebsonsecurity.com/feed/"), "My feed")

    def test_blank_name_uses_a_short_domain_label(self):
        self.assertEqual(source_name_for(None, "https://krebsonsecurity.com/feed/"), "krebsonsecurity")
        self.assertEqual(source_name_for("   ", " https://www.theregister.com/security/headlines.atom "), "theregister")

    def test_www_prefix_is_stripped(self):
        self.assertEqual(default_name_from_url("https://www.bleepingcomputer.com/feed/"), "bleepingcomputer")

    def test_subdomain_becomes_the_label(self):
        # Matches the user-facing rule literally: the first label after the scheme/www.
        self.assertEqual(default_name_from_url("http://export.arxiv.org/rss/cs.CR"), "export")

    def test_port_does_not_leak_into_the_label(self):
        self.assertEqual(default_name_from_url("https://example.com:8443/feed"), "example")

    def test_malformed_link_falls_back_to_the_raw_link(self):
        self.assertEqual(default_name_from_url("not a url"), "not a url")

    def test_neither_name_nor_link_is_refused(self):
        with self.assertRaises(ValueError):
            source_name_for("", None)


if __name__ == "__main__":
    unittest.main()
