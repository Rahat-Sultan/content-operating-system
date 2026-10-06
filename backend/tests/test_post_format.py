"""Plain-text cleanup for generated drafts (no network, no DB)."""
import unittest

from app.workflows.post_format import plain_post_text, strip_title_heading


class TestPlainPostText(unittest.TestCase):
    def test_headings_are_removed_not_kept_as_labels(self):
        text = "## Introduction\nScaling RL is hard.\n\n## Conclusion\nKeep the baseline."
        self.assertEqual(plain_post_text(text), "Scaling RL is hard.\n\nKeep the baseline.")

    def test_bold_and_italic_markers_are_removed_and_words_kept(self):
        out = plain_post_text("The **core problem** is *redundancy* and __cost__ matters.")
        self.assertEqual(out, "The core problem is redundancy and cost matters.")

    def test_bullets_become_bullet_characters(self):
        out = plain_post_text("Steps:\n- pull the base\n* run the trainer")
        self.assertEqual(out, "Steps:\n• pull the base\n• run the trainer")

    def test_code_fences_and_inline_code(self):
        out = plain_post_text("Run `make train`:\n```bash\nmake train\n```\nThen stop.")
        self.assertNotIn("`", out)
        self.assertEqual(out, "Run make train:\nmake train\nThen stop.")

    def test_horizontal_rules_are_dropped(self):
        self.assertEqual(plain_post_text("One.\n\n---\n\nTwo."), "One.\n\nTwo.")

    def test_no_markup_survives_on_a_realistic_draft(self):
        draft = (
            "## Introduction\n\nThe **redundancy** problem is real.\n\n"
            "### Setup\n1. **Pull** the base\n* *Run* the trainer\n\n"
            "Use `adapter_rank` = 8 and see *why*."
        )
        out = plain_post_text(draft)
        for marker in ("#", "**", "__", "`"):
            self.assertNotIn(marker, out)
        self.assertNotIn("\n*", out)

    def test_ordinary_asterisks_in_prose_are_kept(self):
        self.assertEqual(plain_post_text("Keep 2 * 3 = 6 as is."), "Keep 2 * 3 = 6 as is.")


class TestTitleHeading(unittest.TestCase):
    def test_first_heading_becomes_title_and_leaves_body(self):
        title, body = strip_title_heading("# Shared Weights Save Money\n\nThe cost is in the base.")
        self.assertEqual(title, "Shared Weights Save Money")
        self.assertEqual(body, "The cost is in the base.")

    def test_no_heading_keeps_body(self):
        self.assertEqual(strip_title_heading("Just a hook line."), (None, "Just a hook line."))


if __name__ == "__main__":
    unittest.main()
