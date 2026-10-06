"""A source is named after what the user typed, or its link when they typed nothing."""
import unittest

from app.sources.service import source_name_for


class TestSourceNaming(unittest.TestCase):
    def test_typed_name_wins(self):
        self.assertEqual(source_name_for("My feed", "https://a.example/rss"), "My feed")

    def test_blank_name_uses_the_link(self):
        self.assertEqual(source_name_for(None, "https://a.example/rss"), "https://a.example/rss")
        self.assertEqual(source_name_for("   ", " https://a.example/rss "), "https://a.example/rss")

    def test_neither_name_nor_link_is_refused(self):
        with self.assertRaises(ValueError):
            source_name_for("", None)


if __name__ == "__main__":
    unittest.main()
