"""
Chunking pipeline.

Strategy (per schema.md section 4):
- Atomic categories: no chunking, whole text is one record
- Chunked categories: structural split on headings first,
  then semantic split if section > 500 tokens
- Summary: one LLM-generated summary per doc > 2000 tokens total

Token counting uses tiktoken cl100k_base.
Target chunk size: 300-400 tokens. Max: 500 tokens. Min: 50 tokens.
Overlap: 50 tokens between adjacent chunks.
"""

import re
from dataclasses import dataclass, field
from loguru import logger

try:
    import tiktoken

    _enc = tiktoken.get_encoding("cl100k_base")
except Exception:
    _enc = None
    logger.warning("tiktoken not available — using char/4 as token estimate")


# Categories that are always stored as a single atomic record
ATOMIC_CATEGORIES = {
    "faq",
    "objection_response",
    "disclosure",
    "qualification_rule",
    "contact_escalation",
}

# Categories that are chunked
CHUNKED_CATEGORIES = {
    "product_overview",
    "product_coverage",
    "product_exclusions",
    "product_pricing",
    "policy_terms",
    "claim_process",
}

TARGET_TOKENS = 350
MAX_TOKENS = 500
MIN_TOKENS = 50
OVERLAP_TOKENS = 50


def count_tokens(text: str) -> int:
    if _enc:
        return len(_enc.encode(text))
    return len(text) // 4


def encode_tokens(text: str) -> list[int]:
    if _enc:
        return _enc.encode(text)
    return list(range(len(text) // 4))


def decode_tokens(tokens: list[int]) -> str:
    if _enc:
        return _enc.decode(tokens)
    return ""


@dataclass
class Chunk:
    text: str
    section_heading: str = ""
    chunk_index: int = 0
    token_count: int = 0


def chunk_document(text: str, category: str) -> list[Chunk]:
    """
    Chunk a cleaned document according to its category.

    Returns:
        List of Chunk objects. Always at least one chunk.
    """
    if not text or not text.strip():
        return []

    if category in ATOMIC_CATEGORIES:
        return [
            Chunk(
                text=text.strip(),
                section_heading="",
                chunk_index=0,
                token_count=count_tokens(text),
            )
        ]

    if category in CHUNKED_CATEGORIES:
        return _chunk_by_structure(text)

    # Default: treat as chunked
    return _chunk_by_structure(text)


def _extract_sections(text: str) -> list[tuple[str, str]]:
    """
    Split text into (heading, content) pairs by H2/H3 markdown headings.
    Returns list of (heading, body) tuples.
    If no headings found, returns [("", full_text)].
    """
    # Match ## or ### headings
    heading_pattern = re.compile(r"^#{2,3}\s+(.+)$", re.MULTILINE)
    matches = list(heading_pattern.finditer(text))

    if not matches:
        return [("", text)]

    sections = []
    for i, match in enumerate(matches):
        heading = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append((heading, body))

    # Content before first heading
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.insert(0, ("", preamble))

    return sections if sections else [("", text)]


def _split_into_token_chunks(
    text: str,
    heading: str,
    target: int = TARGET_TOKENS,
    max_tokens: int = MAX_TOKENS,
    overlap: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    """
    Split a text block into token-bounded chunks with overlap.
    Splits at sentence boundaries where possible.
    """
    total_tokens = count_tokens(text)

    if total_tokens <= max_tokens:
        return [
            Chunk(
                text=text,
                section_heading=heading,
                token_count=total_tokens,
            )
        ]

    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current_sentences = []
    current_tokens = 0

    for sentence in sentences:
        sentence_tokens = count_tokens(sentence)

        if current_tokens + sentence_tokens > max_tokens and current_sentences:
            chunk_text = " ".join(current_sentences)
            chunks.append(
                Chunk(
                    text=chunk_text,
                    section_heading=heading,
                    token_count=count_tokens(chunk_text),
                )
            )
            # Keep last N tokens worth of sentences as overlap
            overlap_sentences = []
            overlap_count = 0
            for s in reversed(current_sentences):
                s_tokens = count_tokens(s)
                if overlap_count + s_tokens <= overlap:
                    overlap_sentences.insert(0, s)
                    overlap_count += s_tokens
                else:
                    break
            current_sentences = overlap_sentences + [sentence]
            current_tokens = count_tokens(" ".join(current_sentences))
        else:
            current_sentences.append(sentence)
            current_tokens += sentence_tokens

    if current_sentences:
        chunk_text = " ".join(current_sentences)
        if count_tokens(chunk_text) >= MIN_TOKENS:
            chunks.append(
                Chunk(
                    text=chunk_text,
                    section_heading=heading,
                    token_count=count_tokens(chunk_text),
                )
            )

    return (
        chunks
        if chunks
        else [Chunk(text=text, section_heading=heading, token_count=total_tokens)]
    )


def _chunk_by_structure(text: str) -> list[Chunk]:
    """
    Primary chunking strategy: structural then token-based.
    """
    sections = _extract_sections(text)
    all_chunks = []

    for heading, body in sections:
        if not body.strip():
            continue
        token_count = count_tokens(body)
        if token_count <= MAX_TOKENS:
            if token_count >= MIN_TOKENS:
                all_chunks.append(
                    Chunk(
                        text=body,
                        section_heading=heading,
                        token_count=token_count,
                    )
                )
        else:
            sub_chunks = _split_into_token_chunks(body, heading)
            all_chunks.extend(sub_chunks)

    # Re-index
    for i, chunk in enumerate(all_chunks):
        chunk.chunk_index = i

    return (
        all_chunks
        if all_chunks
        else [Chunk(text=text, section_heading="", token_count=count_tokens(text))]
    )


def needs_summary(text: str, threshold: int = 2000) -> bool:
    """Return True if document is long enough to warrant a summary record."""
    return count_tokens(text) > threshold
