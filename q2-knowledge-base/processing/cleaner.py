"""
Text cleaning for raw extracted content.

Removes:
- Markdown image tags: ![...](...)
- Navigation link clusters (lines that are purely markdown links)
- data:image/svg+xml placeholders
- Excessive blank lines (max 2 consecutive)
- Lines shorter than 15 chars that are clearly UI artifacts
  (e.g. "View Plan", "Read More", "Watch Video", "Submit")
- Repeated paragraph blocks (exact string match within same document)

Does NOT:
- Remove tables — these contain premium and coverage data
- Remove numbers or amounts — critical for insurance content
- Do semantic cleaning — that is the chunker's job
"""

import re
from loguru import logger

# UI artifact lines to discard (exact match, case-insensitive, stripped)
_UI_ARTIFACTS = {
    "view plan",
    "read more",
    "watch video",
    "submit",
    "get insured",
    "get a call",
    "buy now",
    "renew now",
    "locate now",
    "view all plans",
    "calculate & proceed",
    "view plan details",
    "know more",
    "click here",
    "learn more",
    "view details",
    "show more",
}


def clean_raw_text(text: str, source_type: str = "web") -> str:
    """
    Clean raw extracted text for a single document.

    Args:
        text: Raw text from crawl or PDF parse
        source_type: "web" or "pdf" — affects cleaning rules

    Returns:
        Cleaned text string. Empty string if nothing meaningful remains.
    """
    if not text:
        return ""

    if source_type == "web":
        text = _clean_web_text(text)
    else:
        text = _clean_pdf_text(text)

    text = _remove_repeated_paragraphs(text)
    text = _normalize_whitespace(text)

    return text.strip()


def _clean_web_text(text: str) -> str:
    # Remove Firecrawl nav list items: - [![](img)](url)\n text
    text = re.sub(r"^-\s*\[!\[.*?\]\(.*?\)\]\(.*?\)\s*$", "", text, flags=re.MULTILINE)
    # Remove data:image/svg+xml placeholders
    text = re.sub(r"!\[.*?\]\(data:image[^)]*\)", "", text)

    # Remove residual list items with only backslashes (Firecrawl nav artifact)
    text = re.sub(r"^-\s*\\\\\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^-\s*\\\s*$", "", text, flags=re.MULTILINE)

    # Remove markdown image tags: ![alt text](url)
    text = re.sub(r"!\[.*?\]\([^)]*\)", "", text)

    # Remove markdown links but keep link text: [text](url) → text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)

    # Remove bare URLs on their own lines
    text = re.sub(r"^https?://\S+$", "", text, flags=re.MULTILINE)

    # Remove UI artifact lines
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.lower() in _UI_ARTIFACTS:
            continue
        # Skip lines that are purely punctuation or special chars
        if stripped and re.match(r"^[#*\-_=|>]+$", stripped):
            continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)
    text = strip_leading_boilerplate(text)

    return text


def _clean_pdf_text(text: str) -> str:
    # Remove page markers we added: [Page N]
    # Keep them as section markers for heading detection
    # but clean up any OCR artifacts around them
    text = re.sub(r"\[Page (\d+)\]", r"\n[Page \1]\n", text)

    # Remove lines that look like page numbers alone
    text = re.sub(r"^\s*\d+\s*$", "", text, flags=re.MULTILINE)

    # Remove repeated header/footer lines
    # (lines appearing 3+ times verbatim are likely headers/footers)
    line_counts: dict[str, int] = {}
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and len(stripped) < 100:
            line_counts[stripped] = line_counts.get(stripped, 0) + 1

    repeated = {line for line, count in line_counts.items() if count >= 3}
    if repeated:
        lines = text.split("\n")
        text = "\n".join(line for line in lines if line.strip() not in repeated)

    return text


def _remove_repeated_paragraphs(text: str) -> str:
    """Remove exact duplicate paragraphs within the same document."""
    paragraphs = text.split("\n\n")
    seen: set[str] = set()
    unique_paragraphs = []
    for para in paragraphs:
        normalized = para.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_paragraphs.append(para)
    return "\n\n".join(unique_paragraphs)


def _normalize_whitespace(text: str) -> str:
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Max 2 consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing whitespace per line
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines)


def strip_leading_boilerplate(text: str, min_line_length: int = 80) -> str:
    """
    Skip leading lines until we hit a heading or a substantive content line.
    Handles nav menus, icon links, and other page furniture at the top of
    web-extracted content.
    """
    lines = text.split("\n")
    start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Stop skipping at a markdown heading
        if stripped.startswith("#"):
            start_idx = i
            break
        # Stop skipping at a substantive line
        if len(stripped) >= min_line_length:
            start_idx = i
            break
    return "\n".join(lines[start_idx:])
