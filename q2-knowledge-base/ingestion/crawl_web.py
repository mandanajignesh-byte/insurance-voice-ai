"""
Web crawler for Star Health pages.

Strategy:
1. Try Firecrawl first (best quality, handles JS-rendered pages).
2. If Firecrawl fails or API key is missing, fall back to trafilatura.
3. Log every attempt and outcome.
4. Never raise — return a RawDocument with status=failed on unrecoverable errors.
"""

import os
import json
from typing import Optional

import trafilatura
import httpx
from dotenv import load_dotenv
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from ingestion.models import RawDocument, ExtractionStatus, SourceType
from ingestion.utils import compute_checksum, clean_extracted_text, utc_now_iso
from ingestion import config as cfg

load_dotenv()


# ── Firecrawl ──────────────────────────────────────────────────────────────────


def _crawl_with_firecrawl(url: str) -> Optional[str]:
    """
    Call Firecrawl API to extract clean markdown/text from a URL.
    Returns extracted text string or None on failure.
    """
    api_key = os.getenv("FIRECRAWL_API_KEY", "").strip()
    if not api_key:
        logger.debug("FIRECRAWL_API_KEY not set — skipping Firecrawl")
        return None

    def _crawl_with_firecrawl(url: str) -> Optional[str]:
        return None  # firecrawl-py SDK version mismatch — trafilatura is primary

    try:
        from firecrawl import FirecrawlApp

        app = FirecrawlApp(api_key=api_key)
        result = app.scrape_url(
            url,
            formats=["markdown"],
            only_main_content=True,
            timeout=cfg.CRAWL_TIMEOUT_SECONDS * 1000,
        )

        # result is a dict with 'markdown', 'metadata', etc.
        if isinstance(result, dict):
            text = result.get("markdown") or result.get("content") or ""
        else:
            # Newer SDK returns an object
            text = (
                getattr(result, "markdown", "") or getattr(result, "content", "") or ""
            )

        if text and len(text.strip()) > cfg.MIN_CONTENT_LENGTH:
            logger.debug(f"Firecrawl succeeded for {url} ({len(text)} chars)")
            return clean_extracted_text(text)
        else:
            logger.warning(f"Firecrawl returned too-short content for {url}")
            return None

    except Exception as e:
        logger.warning(f"Firecrawl failed for {url}: {e}")
        return None


# ── Trafilatura fallback ───────────────────────────────────────────────────────


def _crawl_with_trafilatura(url: str) -> Optional[str]:
    """
    Fetch URL with httpx and extract text with trafilatura.
    Returns extracted text string or None on failure.
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
            url,
            headers=headers,
            timeout=cfg.CRAWL_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
        html = response.text

        text = trafilatura.extract(
            html,
            include_tables=True,
            include_comments=False,
            no_fallback=False,
            favor_recall=True,
        )

        if text and len(text.strip()) > cfg.MIN_CONTENT_LENGTH:
            logger.debug(f"Trafilatura succeeded for {url} ({len(text)} chars)")
            return clean_extracted_text(text)
        else:
            logger.warning(f"Trafilatura returned too-short content for {url}")
            return None

    except Exception as e:
        logger.warning(f"Trafilatura failed for {url}: {e}")
        return None


# ── Public interface ───────────────────────────────────────────────────────────


def crawl_url(target: dict) -> RawDocument:
    """
    Crawl a single URL target from config.
    Tries Firecrawl first, then trafilatura.
    Always returns a RawDocument — never raises.

    Args:
        target: A dict from STAR_HEALTH_WEB_TARGETS with keys:
                url, category, product, doc_id, title
    """
    url = target["url"]
    logger.info(f"Crawling: {url}")

    text = None
    crawler_used = ""

    # Try Firecrawl first
    text = _crawl_with_firecrawl(url)
    if text:
        crawler_used = "firecrawl"

    # Fall back to trafilatura
    if not text:
        logger.info(f"Falling back to trafilatura for {url}")
        text = _crawl_with_trafilatura(url)
        if text:
            crawler_used = "trafilatura"

    # Build the RawDocument
    if text:
        return RawDocument(
            doc_id=target["doc_id"],
            source_url=url,
            source_type=SourceType.WEB,
            configured_title=target["title"],
            configured_category=target["category"],
            configured_product=target["product"],
            raw_text=text,
            char_count=len(text),
            extraction_status=ExtractionStatus.SUCCESS,
            crawler_used=crawler_used,
            checksum=compute_checksum(text),
        )
    else:
        logger.error(f"All crawlers failed for {url}")
        return RawDocument(
            doc_id=target["doc_id"],
            source_url=url,
            source_type=SourceType.WEB,
            configured_title=target["title"],
            configured_category=target["category"],
            configured_product=target["product"],
            raw_text=None,
            char_count=0,
            extraction_status=ExtractionStatus.FAILED,
            extraction_error="Both Firecrawl and trafilatura failed",
            crawler_used="none",
            checksum="",
        )


def crawl_all_web_targets() -> list[RawDocument]:
    """
    Crawl all URLs in STAR_HEALTH_WEB_TARGETS.
    Returns list of RawDocument objects (one per URL, including failures).
    """
    from ingestion.utils import log_separator

    log_separator("Web crawl — Star Health")
    results = []
    for target in cfg.STAR_HEALTH_WEB_TARGETS:
        doc = crawl_url(target)
        results.append(doc)
        status_icon = "✓" if doc.extraction_status == "success" else "✗"
        logger.info(
            f"  {status_icon} {doc.doc_id} | {doc.char_count:,} chars | {doc.crawler_used}"
        )
    return results
