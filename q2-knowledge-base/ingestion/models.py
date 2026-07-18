"""
Pydantic models for raw ingestion output.
These represent what the crawler and PDF parser produce — before cleaning,
chunking, or embedding. The processing step converts these to KB records.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class ExtractionStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"   # content extracted but may be incomplete
    FAILED = "failed"     # extraction failed entirely


class SourceType(str, Enum):
    WEB = "web"
    PDF = "pdf"


class RawDocument(BaseModel):
    """
    One raw document as produced by the ingestion step.
    Saved as one JSON line in the raw JSONL file.
    """

    # Identification
    doc_id: str = Field(description="Source document ID from config (e.g. kb_star_web_001)")
    source_url: str = Field(description="The URL this content was fetched from")
    source_type: SourceType

    # Metadata from config
    configured_title: str = Field(description="Human-readable title from ingestion config")
    configured_category: str = Field(description="Category hint from ingestion config")
    configured_product: str = Field(description="Product slug from ingestion config")

    # Extracted content
    extracted_title: Optional[str] = Field(
        default=None,
        description="Title extracted from the page/PDF itself, if found"
    )
    raw_text: Optional[str] = Field(
        default=None,
        description="Cleaned plain text extracted from HTML or PDF. No HTML tags."
    )
    raw_html: Optional[str] = Field(
        default=None,
        description="Raw HTML returned by crawler. None for PDFs. "
                    "Stored for debugging only — not used downstream."
    )

    # PDF-specific
    page_count: Optional[int] = Field(
        default=None,
        description="Number of pages. Populated for PDFs only."
    )
    pages_extracted: Optional[int] = Field(
        default=None,
        description="Number of pages successfully extracted. Populated for PDFs only."
    )

    # Quality signals
    char_count: int = Field(default=0, description="Character count of raw_text")
    extraction_status: ExtractionStatus = ExtractionStatus.SUCCESS
    extraction_error: Optional[str] = Field(
        default=None,
        description="Error message if extraction failed or was partial"
    )
    crawler_used: str = Field(
        default="",
        description="Which crawler was used: 'firecrawl', 'trafilatura', 'pdfplumber'"
    )

    # Provenance
    crawled_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    checksum: str = Field(
        default="",
        description="SHA-256 of raw_text. Empty if extraction failed."
    )

    class Config:
        use_enum_values = True