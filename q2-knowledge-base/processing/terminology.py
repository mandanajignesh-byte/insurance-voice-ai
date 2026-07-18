"""
Terminology normalization.
Loads alias map from processing/terminology_aliases.json
and normalizes synonym variants to canonical terms.
"""

import json
import re
from pathlib import Path
from loguru import logger

_ALIASES_PATH = Path(__file__).parent / "terminology_aliases.json"


def load_alias_map() -> dict[str, list[str]]:
    """Load alias map from JSON file."""
    if not _ALIASES_PATH.exists():
        logger.warning(
            f"Alias map not found at {_ALIASES_PATH} — skipping normalization"
        )
        return {}
    with open(_ALIASES_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_normalization_patterns(alias_map: dict) -> list[tuple[re.Pattern, str]]:
    """
    Build compiled regex patterns for each alias group.
    Returns list of (pattern, canonical_term) tuples.
    """
    patterns = []
    for canonical, aliases in alias_map.items():
        # All variants including the canonical itself
        all_variants = [canonical] + aliases
        # Sort by length descending so longer matches win
        all_variants.sort(key=len, reverse=True)
        # Escape and join with | for alternation
        pattern_str = r"\b(" + "|".join(re.escape(v) for v in all_variants) + r")\b"
        pattern = re.compile(pattern_str, re.IGNORECASE)
        patterns.append((pattern, canonical))
    return patterns


def normalize_terminology(text: str, patterns: list[tuple[re.Pattern, str]]) -> str:
    """
    Apply terminology normalization to text.
    Replaces all alias variants with their canonical form.
    Preserves original case only when the match IS the canonical term.
    """
    for pattern, canonical in patterns:
        text = pattern.sub(canonical, text)
    return text
