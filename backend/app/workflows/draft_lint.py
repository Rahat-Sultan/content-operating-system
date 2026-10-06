import re
import string
from typing import Any

AI_TELL_PHRASES = [
    "in today's fast-paced",
    "in today's digital age",
    "in the ever-evolving landscape",
    "let's dive in",
    "let's unpack",
    "without further ado",
    "in this article, we will explore",
    "in this post, we will explore",
    "in conclusion",
    "to wrap up",
    "all in all",
    "game-changer",
    "game-changing",
    "unlock the power",
    "what are your thoughts",
    "let me know in the comments",
    "share your thoughts",
]

UNSUPPORTED_EXPERIENCE_PATTERNS = [
    r"\bi've seen\b",
    r"\bin my experience\b",
    r"\bwe spent\b",
    r"\bat my last\b",
    r"\bin our systems\b",
    r"\bin our production\b",
    r"\bwe saw in production\b",
]


def _normalize_words(text: str) -> list[str]:
    """Tokenize into lowercase words stripping punctuation."""
    # Replace punctuation with spaces to avoid hyphen-gluing
    text_clean = text.lower()
    for p in string.punctuation:
        text_clean = text_clean.replace(p, " ")
    return [w for w in text_clean.split() if w]


def lint_draft(
    draft_body: str,
    voice_sample: str | None = None,
    platform: str = "linkedin",
) -> list[dict[str, Any]]:
    """
    Deterministic draft linting function.
    Returns a list of warning dicts:
    [
        {"category": "leakage" | "ai_tell" | "unsupported_experience" | "markdown_syntax", "message": "..."}
    ]
    """
    warnings: list[dict[str, Any]] = []
    if not draft_body:
        return warnings

    draft_lower = draft_body.lower()
    draft_words = _normalize_words(draft_body)


    # 1. Voice-sample leakage: 6 or more consecutive words
    if voice_sample and voice_sample.strip():
        sample_words = _normalize_words(voice_sample)
        if len(sample_words) >= 6:
            # Generate 6-grams from sample
            sample_6grams = {
                " ".join(sample_words[i : i + 6])
                for i in range(len(sample_words) - 5)
            }
            # Check draft 6-grams
            found_leakages = set()
            for i in range(len(draft_words) - 5):
                candidate = " ".join(draft_words[i : i + 6])
                if candidate in sample_6grams:
                    found_leakages.add(candidate)

            for leak in sorted(found_leakages):
                warnings.append({
                    "category": "leakage",
                    "message": f"Voice-sample leakage detected: '{leak}'",
                })

    # 2. AI-tell phrases
    for tell in AI_TELL_PHRASES:
        if tell in draft_lower:
            warnings.append({
                "category": "ai_tell",
                "message": f"Detected generic AI-tell phrase: '{tell}'",
            })

    # 3. Unsupported experience claims
    for pattern in UNSUPPORTED_EXPERIENCE_PATTERNS:
        match = re.search(pattern, draft_lower)
        if match:
            warnings.append({
                "category": "unsupported_experience",
                "message": f"Potential unsupported experience claim flagged: '{match.group(0)}'",
            })

    # 4. Markdown syntax detection (CP-3.4: drafts for LinkedIn should be clean plain text)
    if platform.lower() == "linkedin":
        # Check for markdown headings (#, ##, ###)
        if re.search(r"^\s*#{1,6}\s+", draft_body, flags=re.MULTILINE):
            warnings.append({
                "category": "markdown_syntax",
                "message": "Markdown headings (# / ##) detected. LinkedIn drafts should use plain text line breaks.",
            })
        # Check for bold / italic markers (**bold** or *italic*)
        if re.search(r"\*\*[^*]+\*\*|(?<!\w)_[^_]+_(?!\w)", draft_body):
            warnings.append({
                "category": "markdown_syntax",
                "message": "Markdown bold/italic syntax (** / _) detected. LinkedIn does not render markdown formatting.",
            })
        # Check for markdown links [text](url)
        if re.search(r"\[([^\]]+)\]\(([^)]+)\)", draft_body):
            warnings.append({
                "category": "markdown_syntax",
                "message": "Markdown link syntax [text](url) detected. Use plain text format: 'text (url)'.",
            })

    return warnings


