"""
Pydantic model for a processed KB record.
Matches the schema defined in q2-knowledge-base/schema.md exactly.
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class KBRecord(BaseModel):
    record_id: str
    title: str
    content: str
    content_type: str  # "chunk" | "atomic" | "summary"
    category: str
    product: str
    language: str = "en"
    source_url: str
    source_document_id: str
    source_document_title: str
    section_heading: str = ""
    chunk_index: int = 0
    chunk_total: int = 1
    page_number: Optional[int] = None
    version: str
    superseded_by: Optional[str] = None
    ingested_at: str
    extraction_status: str
    has_pii: bool = False
    pii_types: list[str] = Field(default_factory=list)
    terminology_normalized: bool = False
    checksum: str
    verbatim_required: bool = False

    class Config:
        use_enum_values = True


class KBDocument(BaseModel):
    source_document_id: str
    source_document_title: str
    source_url: str
    language: str = "en"
    version: str
    ingested_at: str
    extraction_status: str
    total_chunks: int
    chunk_ids: list[str]
    summary_record_id: Optional[str] = None
    checksum: str
