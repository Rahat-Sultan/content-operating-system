import re
from typing import Tuple

LINKEDIN_CHAR_LIMIT = 3000


def normalize_title_for_comparison(text: str) -> str:
    """Normalize text for title duplicate comparison (case and punctuation insensitive)."""
    # Remove markdown formatting, hashtags, and non-alphanumeric chars
    cleaned = re.sub(r"[#*_`~\[\]()]", "", text)
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    return " ".join(cleaned.lower().split())


def render_for_linkedin(title: str | None, markdown_body: str) -> Tuple[str, bool]:
    """
    Pure function that renders markdown content into LinkedIn-compliant plain text.
    Returns (rendered_text, was_truncated).
    
    Rules:
    1. Drop #, ##, ### heading markers; keep the heading text on its own line with blank line before/after.
    2. Remove a leading H1 or first line that duplicates the title (case- and punctuation-insensitive).
    3. **bold** / __bold__ and *italic* / _italic_ -> plain text (no unicode fake-bold).
    4. Bullets '-' / '*' -> '•'; numbered lists stay numbered.
    5. Links [text](url) -> 'text (url)'.
    6. Code fences removed but code content kept on its own lines; inline backticks removed.
    7. Tables and horizontal rules converted to plain lines or dropped.
    8. Collapse runs of 3+ blank lines to 2; trim trailing whitespace.
    9. Prepend title if present (and not already duplicated).
    10. Truncate after rendering to 3,000 chars at paragraph or sentence boundary (never mid-word).
    """
    body = markdown_body or ""
    clean_title = (title or "").strip()

    # 1. Normalize line endings
    text = body.replace("\r\n", "\n").replace("\r", "\n")

    # 2. Check if first line duplicates title
    lines = text.split("\n")
    first_non_empty_idx = -1
    for idx, l in enumerate(lines):
        if l.strip():
            first_non_empty_idx = idx
            break

    if clean_title and first_non_empty_idx != -1:
        first_line_raw = lines[first_non_empty_idx].strip()
        # Strip heading markers from first line to compare
        first_line_clean = re.sub(r"^#+\s*", "", first_line_raw).strip()
        if normalize_title_for_comparison(clean_title) == normalize_title_for_comparison(first_line_clean):
            # Duplicate of title; remove this line
            lines.pop(first_non_empty_idx)
            text = "\n".join(lines)

    # 3. Strip code fences (```lang ... ```)
    # Remove ```python or ``` fences, keep code block lines
    text = re.sub(r"```[a-zA-Z0-9_-]*\n", "\n", text)
    text = re.sub(r"```", "", text)

    # 4. Remove inline backticks
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 5. Convert markdown links: [text](url) -> text (url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)

    # 6. Drop horizontal rules (---, ***, ___ on own line)
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # 7. Convert table rows: | col1 | col2 | -> col1 | col2, drop separator |--|--|
    new_lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Table separator line e.g. |---|---|
        if re.match(r"^\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?$", stripped):
            continue
        # Table data line e.g. | foo | bar |
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            new_lines.append(" | ".join(cells))
            continue
        new_lines.append(line)
    text = "\n".join(new_lines)

    # 8. Convert headings: # Heading -> \nHeading\n
    # Handle #, ##, ###, ####, etc.
    text = re.sub(r"^\s*#{1,6}\s+(.+)$", r"\n\1\n", text, flags=re.MULTILINE)

    # 9. Bold and Italic markers: **bold**, __bold__, *italic*, _italic_
    # Bold **text** and __text__
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    # Italic *text* and _text_
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)

    # 10. Bullets: lines starting with * or - followed by space -> •
    text = re.sub(r"^(\s*)[*-]\s+", r"\1• ", text, flags=re.MULTILINE)

    # 11. Combine title and body
    if clean_title:
        full_text = f"{clean_title}\n\n{text.strip()}"
    else:
        full_text = text.strip()

    # 12. Collapse runs of 3+ blank lines to 2, trim trailing whitespace per line
    processed_lines = [l.rstrip() for l in full_text.split("\n")]
    full_text = "\n".join(processed_lines)
    full_text = re.sub(r"\n{3,}", "\n\n", full_text).strip()

    # 13. Platform length limit (3,000 chars) truncation at paragraph or sentence boundary
    was_truncated = False
    if len(full_text) > LINKEDIN_CHAR_LIMIT:
        was_truncated = True
        truncated = full_text[:LINKEDIN_CHAR_LIMIT]

        # Try to find a paragraph break (\n\n) within the last 500 chars of limit
        last_para = truncated.rfind("\n\n")
        if last_para > LINKEDIN_CHAR_LIMIT - 600:
            full_text = truncated[:last_para].rstrip()
        else:
            # Try to find a sentence ending (.!?) followed by space or newline
            sentence_matches = list(re.finditer(r"[.!?](\s|\n)", truncated))
            if sentence_matches and sentence_matches[-1].end() > LINKEDIN_CHAR_LIMIT - 500:
                full_text = truncated[: sentence_matches[-1].end()].rstrip()
            else:
                # Mid-word fallback: truncate at last whitespace
                last_space = truncated.rfind(" ")
                if last_space > 0:
                    full_text = truncated[:last_space].rstrip()
                else:
                    full_text = truncated.rstrip()

    return full_text, was_truncated
