import unittest
from app.workflows.draft_lint import lint_draft

class TestDraftLint(unittest.TestCase):
    def test_clean_draft(self):
        draft = """# Architecture of Vector Databases
        
Vector databases store high-dimensional embeddings and query them with approximate nearest neighbor algorithms like HNSW. 
The trade-off is between indexing memory overhead and query latency. For large-scale systems, memory bandwidth becomes the primary bottleneck rather than CPU cycles."""
        
        warnings = lint_draft(draft, voice_sample="Write bluntly and avoid hype.")
        self.assertEqual(len(warnings), 0, f"Expected 0 warnings, got: {warnings}")

    def test_voice_sample_leakage(self):
        sample = "We spent three weeks chasing our tails because the cache layer broke."
        draft = "In this scenario, we spent three weeks chasing our tails because the system lacked backpressure."
        warnings = lint_draft(draft, voice_sample=sample)
        categories = [w["category"] for w in warnings]
        self.assertIn("leakage", categories)
        self.assertTrue(any("we spent three weeks chasing our" in w["message"] for w in warnings))

    def test_ai_tells(self):
        draft = "In today's fast-paced world, let's dive in. In conclusion, this is a game-changer. What are your thoughts?"
        warnings = lint_draft(draft)
        categories = [w["category"] for w in warnings]
        self.assertIn("ai_tell", categories)
        messages = [w["message"] for w in warnings]
        self.assertTrue(any("in today's fast-paced" in m for m in messages))
        self.assertTrue(any("let's dive in" in m for m in messages))
        self.assertTrue(any("in conclusion" in m for m in messages))
        self.assertTrue(any("game-changer" in m for m in messages))
        self.assertTrue(any("what are your thoughts" in m for m in messages))

    def test_unsupported_experience_claims(self):
        draft = "I've seen many companies fail at this. In my experience, at my last company we struggled."
        warnings = lint_draft(draft)
        categories = [w["category"] for w in warnings]
        self.assertIn("unsupported_experience", categories)
        messages = [w["message"] for w in warnings]
        self.assertTrue(any("i've seen" in m for m in messages))
        self.assertTrue(any("in my experience" in m for m in messages))
        self.assertTrue(any("at my last" in m for m in messages))

if __name__ == "__main__":
    unittest.main()
