"""
Plain-text cleanup for generated LinkedIn drafts.

The writer prompt asks for plain text, but free models often ignore that and return
headings and bold. This module removes the markup in code, so the draft a human
reviews reads like a post, not a Markdown document. It runs once, when a version is
generated. Stored versions are never edited afterwards (ADR-008).
"""
import re

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+")
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_ITALIC = re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])|(?<![\w_])_(?=\S)(.+?)(?<=\S)_(?![\w_])")
_CODE_FENCE = re.compile(r"^\s*```[\w-]*\s*$")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_RULE = re.compile(r"^\s*([-*_])\s*(\1\s*){2,}$")


def strip_title_heading(body: str) -> tuple[str | None, str]:
    """If the first line is a Markdown heading, returns (heading text, body without it)."""
    lines = body.strip().split("\n")
    m = _HEADING.match(lines[0]) if lines else None
    if not m:
        return None, body.strip()
    return m.group(1).strip(), "\n".join(lines[1:]).strip()


def plain_post_text(text: str) -> str:
    out: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if _CODE_FENCE.match(line) or _RULE.match(line):
            continue
        if _HEADING.match(line):
            # Section labels ("Introduction", "Conclusion") read as a template, not a post.
            continue
        line = _BULLET.sub(lambda m: f"{m.group(1)}• ", line)
        line = _BOLD.sub(r"\2", line)
        line = _ITALIC.sub(lambda m: m.group(1) or m.group(2), line)
        line = _INLINE_CODE.sub(r"\1", line)
        out.append(line.rstrip())
    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
