"""
PDF ingestion for Star Health brochures.

Downloads PDFs from the URLs in config, extracts text page by page using
pdfplumber, and returns RawDocument objects.

Design choices:
- pdfplumber instead of Docling: runs on CPU with no install dependencies.
  Docling (better for complex layouts) will be used on Kaggle in a later step
  if pdfplumber output quality is insufficient.
- Download to a temp file, parse, then discard the binary — we only keep text.
- Tables are extracted as pipe-delimited text inline with the content.
"""

import io
import tempfile
from pathlib import Path
from typing import Optional

import httpx
import pdfplumber
from loguru import logger

from ingestion.models import RawDocument, ExtractionStatus, SourceType
from ingestion.utils import compute_checksum, clean_extracted_text
from ingestion import config as cfg


def _download_pdf(url: str, timeout: int = 60) -> Optional[bytes]:
    """
    Download a PDF from a URL and return raw bytes.
    Returns None on failure.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        response = httpx.get(
            url, headers=headers, timeout=timeout, follow_redirects=True
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "pdf" not in content_type.lower() and not url.lower().endswith(".pdf"):
            logger.warning(
                f"URL may not be a PDF (content-type: {content_type}): {url}"
            )
        return response.content
    except Exception as e:
        logger.error(f"Failed to download PDF from {url}: {e}")
        return None


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> tuple[Optional[str], int, int]:
    """
    Extract text from PDF bytes using pdfplumber.

    Returns:
        (extracted_text, page_count, pages_extracted)
        extracted_text is None if extraction failed entirely.
    """
    page_texts = []
    page_count = 0
    pages_extracted = 0

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            page_count = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                try:
                    # Extract plain text
                    text = page.extract_text(x_tolerance=3, y_tolerance=3) or ""

                    # Extract tables and append as pipe-delimited text
                    tables = page.extract_tables()
                    table_texts = []
                    for table in tables:
                        for row in table:
                            cleaned_row = [
                                str(cell).strip() if cell else "" for cell in row
                            ]
                            table_texts.append(" | ".join(cleaned_row))
                    if table_texts:
                        text = text + "\n\n" + "\n".join(table_texts)

                    if text.strip():
                        page_texts.append(f"[Page {i + 1}]\n{text.strip()}")
                        pages_extracted += 1

                except Exception as e:
                    logger.warning(f"Failed to extract page {i + 1}: {e}")

    except Exception as e:
        logger.error(f"pdfplumber failed to open PDF: {e}")
        return None, page_count, pages_extracted

    if not page_texts:
        return None, page_count, pages_extracted

    full_text = "\n\n".join(page_texts)
    return clean_extracted_text(full_text), page_count, pages_extracted


def parse_pdf_url(target: dict) -> RawDocument:
    """
    Download and parse a single PDF target from config.
    Always returns a RawDocument — never raises.

    Args:
        target: A dict from STAR_HEALTH_PDF_TARGETS with keys:
                url, category, product, doc_id, title
    """
    url = target["url"]
    logger.info(f"Downloading PDF: {url}")

    pdf_bytes = _download_pdf(url)
    if not pdf_bytes:
        return RawDocument(
            doc_id=target["doc_id"],
            source_url=url,
            source_type=SourceType.PDF,
            configured_title=target["title"],
            configured_category=target["category"],
            configured_product=target["product"],
            raw_text=None,
            char_count=0,
            extraction_status=ExtractionStatus.FAILED,
            extraction_error="PDF download failed",
            crawler_used="pdfplumber",
            checksum="",
        )

    logger.info(f"Downloaded {len(pdf_bytes):,} bytes — extracting text")
    text, page_count, pages_extracted = _extract_text_from_pdf_bytes(pdf_bytes)

    if not text:
        return RawDocument(
            doc_id=target["doc_id"],
            source_url=url,
            source_type=SourceType.PDF,
            configured_title=target["title"],
            configured_category=target["category"],
            configured_product=target["product"],
            raw_text=None,
            page_count=page_count,
            pages_extracted=0,
            char_count=0,
            extraction_status=ExtractionStatus.FAILED,
            extraction_error="pdfplumber extracted no text (possibly scanned PDF)",
            crawler_used="pdfplumber",
            checksum="",
        )

    status = (
        ExtractionStatus.SUCCESS
        if pages_extracted == page_count
        else ExtractionStatus.PARTIAL
    )

    return RawDocument(
        doc_id=target["doc_id"],
        source_url=url,
        source_type=SourceType.PDF,
        configured_title=target["title"],
        configured_category=target["category"],
        configured_product=target["product"],
        raw_text=text,
        page_count=page_count,
        pages_extracted=pages_extracted,
        char_count=len(text),
        extraction_status=status,
        extraction_error=(
            f"Only {pages_extracted}/{page_count} pages extracted"
            if status == ExtractionStatus.PARTIAL
            else None
        ),
        crawler_used="pdfplumber",
        checksum=compute_checksum(text),
    )


def parse_all_pdf_targets() -> list[RawDocument]:
    """
    Download and parse all PDFs in STAR_HEALTH_PDF_TARGETS.
    Returns list of RawDocument objects.
    """
    from ingestion.utils import log_separator

    log_separator("PDF ingestion — Star Health")
    results = []
    for target in cfg.STAR_HEALTH_PDF_TARGETS:
        doc = parse_pdf_url(target)
        results.append(doc)
        status_icon = "✓" if doc.extraction_status == "success" else "✗"
        logger.info(
            f"  {status_icon} {doc.doc_id} | "
            f"{doc.char_count:,} chars | "
            f"pages {doc.pages_extracted}/{doc.page_count}"
        )
    return results


def parse_local_pdf(target: dict) -> RawDocument:
    """
    Parse a PDF from a local file path.
    Used when the PDF cannot be downloaded programmatically.
    """
    file_path = Path(target["file_path"])
    logger.info(f"Parsing local PDF: {file_path.name}")

    if not file_path.exists():
        logger.error(f"Local PDF not found: {file_path}")
        return RawDocument(
            doc_id=target["doc_id"],
            source_url=target["source_url"],
            source_type=SourceType.PDF,
            configured_title=target["title"],
            configured_category=target["category"],
            configured_product=target["product"],
            raw_text=None,
            char_count=0,
            extraction_status=ExtractionStatus.FAILED,
            extraction_error=f"Local file not found: {file_path}",
            crawler_used="pdfplumber_local",
            checksum="",
        )

    pdf_bytes = file_path.read_bytes()
    text, page_count, pages_extracted = _extract_text_from_pdf_bytes(pdf_bytes)

    if not text:
        return RawDocument(
            doc_id=target["doc_id"],
            source_url=target["source_url"],
            source_type=SourceType.PDF,
            configured_title=target["title"],
            configured_category=target["category"],
            configured_product=target["product"],
            raw_text=None,
            page_count=page_count,
            pages_extracted=0,
            char_count=0,
            extraction_status=ExtractionStatus.FAILED,
            extraction_error="pdfplumber extracted no text (possibly scanned/image PDF)",
            crawler_used="pdfplumber_local",
            checksum="",
        )

    status = (
        ExtractionStatus.SUCCESS
        if pages_extracted == page_count
        else ExtractionStatus.PARTIAL
    )

    return RawDocument(
        doc_id=target["doc_id"],
        source_url=target["source_url"],
        source_type=SourceType.PDF,
        configured_title=target["title"],
        configured_category=target["category"],
        configured_product=target["product"],
        raw_text=text,
        page_count=page_count,
        pages_extracted=pages_extracted,
        char_count=len(text),
        extraction_status=status,
        extraction_error=(
            f"Only {pages_extracted}/{page_count} pages extracted"
            if status == ExtractionStatus.PARTIAL
            else None
        ),
        crawler_used="pdfplumber_local",
        checksum=compute_checksum(text),
    )


def parse_all_local_pdfs() -> list[RawDocument]:
    """Parse all locally stored PDFs defined in config.LOCAL_PDF_TARGETS."""
    from ingestion.utils import log_separator

    log_separator("Local PDF ingestion — Star Health")
    results = []
    for target in cfg.LOCAL_PDF_TARGETS:
        doc = parse_local_pdf(target)
        results.append(doc)
        status_icon = "✓" if doc.extraction_status == "success" else "✗"
        logger.info(
            f"  {status_icon} {doc.doc_id} | "
            f"{doc.char_count:,} chars | "
            f"pages {doc.pages_extracted}/{doc.page_count}"
        )
    return results
