"""
Processing pipeline entry point.

Reads all raw JSONL files, applies:
1. Text cleaning
2. Terminology normalization
3. PII detection and redaction
4. Chunking
5. Record ID generation

Writes:
- q2-knowledge-base/data/processed/kb_records.jsonl
- q2-knowledge-base/data/processed/kb_documents.jsonl

Usage:
    python -m processing.run
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingestion.models import RawDocument, ExtractionStatus
from processing.models import KBRecord, KBDocument
from processing.cleaner import clean_raw_text
from processing.terminology import (
    load_alias_map,
    build_normalization_patterns,
    normalize_terminology,
)
from processing.pii import detect_and_redact
from processing.chunker import chunk_document, needs_summary, count_tokens

load_dotenv()

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "q2-knowledge-base" / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "q2-knowledge-base" / "data" / "processed"

RAW_FILES = [
    RAW_DIR / "star_health_web_raw.jsonl",
    RAW_DIR / "star_health_local_pdf_raw.jsonl",
    RAW_DIR / "star_health_pdf_raw.jsonl",
]

KB_RECORDS_FILE = PROCESSED_DIR / "kb_records.jsonl"
KB_DOCUMENTS_FILE = PROCESSED_DIR / "kb_documents.jsonl"
PROCESSING_LOG = PROCESSED_DIR / "processing.log"

# ── Logging ───────────────────────────────────────────────────────────────────

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    level="INFO",
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def version_string() -> str:
    return datetime.now(timezone.utc).strftime("%Y.%m")


def make_record_id(
    source: str, category: str, doc_seq: int, chunk_index: int = -1
) -> str:
    """
    Generate a human-readable record ID.
    Format: kb_{source}_{cat_short}_{doc_seq:03d} for atomics
            kb_{source}_{cat_short}_{doc_seq:03d}_c{chunk:03d} for chunks
    """
    # Source abbreviation
    src_map = {
        "kb_star_web": "star_web",
        "kb_star_pdf": "star_pdf",
    }
    # Category short code
    cat_map = {
        "product_overview": "ov",
        "product_coverage": "cov",
        "product_exclusions": "excl",
        "product_pricing": "price",
        "qualification_rule": "qual",
        "policy_terms": "pol",
        "claim_process": "claim",
        "faq": "faq",
        "objection_response": "obj",
        "disclosure": "disc",
        "contact_escalation": "contact",
    }
    cat_short = cat_map.get(category, category[:4])
    base = f"kb_star_{cat_short}_{doc_seq:03d}"
    if chunk_index >= 0:
        return f"{base}_c{chunk_index:03d}"
    return base


def compute_checksum(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_raw_documents() -> list[RawDocument]:
    """Load all raw documents from all JSONL files. Skip missing files."""
    docs = []
    for path in RAW_FILES:
        if not path.exists():
            logger.warning(f"Raw file not found, skipping: {path.name}")
            continue
        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    doc = RawDocument(**data)
                    if doc.extraction_status in ("success", "partial") and doc.raw_text:
                        docs.append(doc)
                    else:
                        logger.debug(
                            f"Skipping {doc.doc_id} — status={doc.extraction_status}"
                        )
                except Exception as e:
                    logger.warning(f"{path.name}:{line_num} — failed to parse: {e}")
    return docs


# ── Main pipeline ─────────────────────────────────────────────────────────────


def process_document(
    raw_doc: RawDocument,
    doc_seq: int,
    norm_patterns: list,
    version: str,
) -> tuple[list[KBRecord], KBDocument]:
    """
    Process one raw document into KB records.

    Returns:
        (list of KBRecord, KBDocument manifest)
    """
    doc_id = raw_doc.doc_id
    logger.info(f"Processing {doc_id} ({raw_doc.char_count:,} chars)")

    # 1. Clean
    cleaned = clean_raw_text(raw_doc.raw_text, source_type=raw_doc.source_type)
    if not cleaned:
        logger.warning(f"  {doc_id}: empty after cleaning — skipping")
        return [], None

    # 2. Terminology normalization
    normalized = normalize_terminology(cleaned, norm_patterns)
    terminology_was_applied = normalized != cleaned

    # 3. PII detection and redaction
    pii_result = detect_and_redact(normalized)
    final_text = pii_result.redacted_text

    # 4. Chunk
    category = raw_doc.configured_category
    chunks = chunk_document(final_text, category)
    if not chunks:
        logger.warning(f"  {doc_id}: no chunks produced — skipping")
        return [], None

    logger.info(f"  → {len(chunks)} chunks, PII={pii_result.has_pii}")

    # 5. Build KB records
    records = []
    ingested_at = utc_now()
    chunk_total = len(chunks)

    for chunk in chunks:
        chunk_idx = chunk.chunk_index
        record_id = make_record_id(doc_id, category, doc_seq, chunk_idx)

        record = KBRecord(
            record_id=record_id,
            title=(
                f"{raw_doc.configured_title} — {chunk.section_heading}"
                if chunk.section_heading
                else raw_doc.configured_title
            ),
            content=chunk.text,
            content_type="chunk" if chunk_total > 1 else "atomic",
            category=category,
            product=raw_doc.configured_product,
            language="en",
            source_url=raw_doc.source_url,
            source_document_id=doc_id,
            source_document_title=raw_doc.configured_title,
            section_heading=chunk.section_heading,
            chunk_index=chunk_idx,
            chunk_total=chunk_total,
            page_number=(
                raw_doc.page_number if hasattr(raw_doc, "page_number") else None
            ),
            version=version,
            superseded_by=None,
            ingested_at=ingested_at,
            extraction_status=raw_doc.extraction_status,
            has_pii=pii_result.has_pii,
            pii_types=pii_result.pii_types,
            terminology_normalized=terminology_was_applied,
            checksum=compute_checksum(chunk.text),
        )
        records.append(record)

    # 6. Build document manifest
    doc_manifest = KBDocument(
        source_document_id=doc_id,
        source_document_title=raw_doc.configured_title,
        source_url=raw_doc.source_url,
        language="en",
        version=version,
        ingested_at=ingested_at,
        extraction_status=raw_doc.extraction_status,
        total_chunks=chunk_total,
        chunk_ids=[r.record_id for r in records],
        summary_record_id=None,
        checksum=raw_doc.checksum,
    )

    return records, doc_manifest


def load_manual_records() -> list[KBRecord]:
    """Load manually authored records from samples directory."""
    manual_path = (
        REPO_ROOT / "q2-knowledge-base" / "data" / "samples" / "manual_records.jsonl"
    )
    if not manual_path.exists():
        logger.warning("No manual records file found — skipping")
        return []
    records = []
    with open(manual_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(KBRecord(**json.loads(line)))
            except Exception as e:
                logger.warning(f"Manual record parse error: {e}")
    logger.info(f"Loaded {len(records)} manual records")
    return records


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    logger.add(PROCESSING_LOG, rotation="10 MB", level="DEBUG")

    version = version_string()
    logger.info("=" * 60)
    logger.info("Processing pipeline — Star Health KB")
    logger.info(f"Version: {version}")
    logger.info("=" * 60)

    # Load alias map
    alias_map = load_alias_map()
    norm_patterns = build_normalization_patterns(alias_map)
    logger.info(f"Loaded {len(alias_map)} terminology alias groups")

    # Load raw documents
    raw_docs = load_raw_documents()
    logger.info(f"Loaded {len(raw_docs)} raw documents to process")

    all_records: list[KBRecord] = []
    all_documents: list[KBDocument] = []
    failed = 0

    for seq, raw_doc in enumerate(raw_docs):
        try:
            records, doc_manifest = process_document(
                raw_doc=raw_doc,
                doc_seq=seq,
                norm_patterns=norm_patterns,
                version=version,
            )
            if records:
                all_records.extend(records)
                all_documents.append(doc_manifest)
        except Exception as e:
            logger.error(f"Failed to process {raw_doc.doc_id}: {e}")
            failed += 1
    # Merge manual records
    manual_records = load_manual_records()
    all_records.extend(manual_records)

    # Write output
    with open(KB_RECORDS_FILE, "w", encoding="utf-8") as f:
        for record in all_records:
            f.write(record.model_dump_json() + "\n")

    with open(KB_DOCUMENTS_FILE, "w", encoding="utf-8") as f:
        for doc in all_documents:
            f.write(doc.model_dump_json() + "\n")

    # Summary
    logger.info("=" * 60)
    logger.info(f"Documents processed : {len(all_documents)}")
    logger.info(f"Documents failed    : {failed}")
    logger.info(f"Total KB records    : {len(all_records)}")
    logger.info(f"Output              : {KB_RECORDS_FILE}")
    logger.info("=" * 60)

    # Quick stats by category
    from collections import Counter

    cat_counts = Counter(r.category for r in all_records)
    logger.info("Records by category:")
    for cat, count in sorted(cat_counts.items()):
        logger.info(f"  {cat:<25} {count}")


if __name__ == "__main__":
    main()
