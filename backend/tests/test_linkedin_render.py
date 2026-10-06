import unittest
from app.publishing.render import render_for_linkedin, normalize_title_for_comparison, LINKEDIN_CHAR_LIMIT


class TestRenderForLinkedIn(unittest.TestCase):
    def test_cp_3_2_real_draft_opening_a(self):
        title = "Building Multi-Agent RL Systems with Open-Weight Decision Models: Lessons from Clef's RL Fine-Tuning Platform"
        body = """# Building Multi-Agent RL Systems with Open-Weight Decision Models: Lessons from Clef's RL Fine-Tuning Platform

## Introduction
Multi-agent reinforcement learning (MARL) presents unique stability challenges when scaling beyond single-agent environments.

### Mechanics
We observed that asynchronous gradient updates lead to policy divergence unless constrained by trust-region boundaries."""

        rendered, was_truncated = render_for_linkedin(title, body)

        # Assert no markdown heading markers
        self.assertNotIn("#", rendered)
        self.assertNotIn("##", rendered)
        self.assertNotIn("###", rendered)
        # Title appears exactly once (not duplicated in body)
        self.assertEqual(rendered.count("Lessons from Clef"), 1)
        self.assertFalse(was_truncated)
        self.assertIn("Introduction", rendered)
        self.assertIn("Mechanics", rendered)

    def test_cp_3_2_real_draft_opening_b(self):
        title = "Why a stronger hash can silently break supply-chain trust"
        body = """# Why a stronger hash can silently break supply-chain trust

*Why a stronger hash can silently break supply-chain trust*

When Git introduces SHA-256 object formats, legacy signature verification scripts can silently reject new commits.
**The core trade-off** is backward compatibility versus cryptographic collision resistance."""

        rendered, was_truncated = render_for_linkedin(title, body)

        self.assertNotIn("#", rendered)
        self.assertNotIn("**", rendered)
        self.assertNotIn("*", rendered)
        self.assertIn("The core trade-off is backward compatibility", rendered)
        self.assertFalse(was_truncated)

    def test_cp_3_2_full_construct_coverage(self):
        title = "Mastering Systems Engineering"
        body = """# Mastering Systems Engineering

## Overview
Here is a paragraph with **bold text**, __also bold__, *italic text*, and _italic too_.
Check out this inline code: `const x = 42;` and link: [Documentation](https://example.com/docs).

### Code Block
```python
def process_stream():
    return True
```

### Table & Separator
| Component | Latency | Overhead |
|---|---|---|
| Ingress | 2ms | Low |
| DB Engine | 15ms | High |

---

### Bullets & Lists
- First bullet item
* Second bullet item
1. Numbered step 1
2. Numbered step 2

A lot of whitespace follows.




Final paragraph."""

        rendered, was_truncated = render_for_linkedin(title, body)

        # Assert output contains NO markdown syntax
        self.assertNotIn("#", rendered)
        self.assertNotIn("**", rendered)
        self.assertNotIn("__", rendered)
        self.assertNotIn("`", rendered)
        self.assertNotIn("[Documentation]", rendered)
        self.assertNotIn("---", rendered)
        self.assertNotIn("```", rendered)

        # Check conversions
        self.assertIn("Documentation (https://example.com/docs)", rendered)
        self.assertIn("• First bullet item", rendered)
        self.assertIn("• Second bullet item", rendered)
        self.assertIn("1. Numbered step 1", rendered)
        self.assertIn("def process_stream():", rendered)
        self.assertIn("Ingress | 2ms | Low", rendered)

        # Assert title appears once
        self.assertEqual(rendered.count("Mastering Systems Engineering"), 1)

        # Runs of 3+ blank lines collapsed
        self.assertNotIn("\n\n\n", rendered)
        self.assertFalse(was_truncated)

    def test_cp_3_2_truncation_on_boundary(self):
        title = "Long Post Analysis"
        # Generate a post exceeding 3,000 characters with distinct sentences
        sentences = [
            f"Sentence number {i} describes system architecture and latency tradeoffs in depth."
            for i in range(70)
        ]
        body = "\n\n".join(sentences)
        self.assertGreater(len(body), 3500)

        rendered, was_truncated = render_for_linkedin(title, body)
        self.assertTrue(was_truncated)
        self.assertLessEqual(len(rendered), LINKEDIN_CHAR_LIMIT)
        # Ensure it didn't cut mid-word (ends on punctuation or whitespace boundary)
        self.assertTrue(
            rendered.endswith(".") or rendered.endswith("!") or rendered.endswith("?") or rendered[-1].isalnum()
        )
        last_word = rendered.split()[-1]
        self.assertIn(last_word, ["depth.", "depth", "depth!", "depth?"])


if __name__ == "__main__":
    unittest.main()
