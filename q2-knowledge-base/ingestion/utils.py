"""
Shared utilities for the ingestion pipeline.
"""

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger


def compute_checksum(text: str) -> str:
    """Return SHA-256 hex digest of text, prefixed with 'sha256:'."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def clean_extracted_text(text: str) -> str:
    """
    Light cleaning of raw extracted text.
    Removes excessive whitespace and blank lines.
    Does NOT do semantic cleaning — that is the processing step's job.
    """
    if not text:
        return ""
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse more than two consecutive newlines into two
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip trailing whitespace from each line
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    # Strip leading/trailing whitespace from the whole document
    return text.strip()


def ensure_dir(path: Path) -> None:
    """Create directory if it does not exist."""
    path.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def log_separator(label: str) -> None:
    """Log a visible section separator."""
    logger.info("─" * 60)
    logger.info(f"  {label}")
    logger.info("─" * 60)