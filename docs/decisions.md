# Design Decisions

This document records notable technical decisions as they are made during implementation, in ADR-lite form: context, decision, alternatives considered, consequences.

Entries will be added as each question is implemented.
## ADR-001: Multi-path ingestion with manual PDF download fallback

**Date**: 2026-07

**Context**: Star Health's website rate-limits automated crawlers after the
first 1-2 requests. Product detail pages return empty content or timeout.
PDF brochure URLs on starhealth.in are blocked programmatically.

**Decision**: Use a three-path ingestion strategy:
1. Firecrawl (primary) for JS-rendered pages where it succeeds
2. Trafilatura (fallback) for server-rendered pages
3. Manual browser download + local pdfplumber parse for PDFs

CDN-hosted PDF URLs (d28c6jni2fmamz.cloudfront.net) were extracted from
successfully crawled pages and downloaded manually via browser.

**Alternatives considered**: Crawl4AI with Playwright (would handle JS
rendering but still subject to IP-level rate limiting after initial
requests). Scrapy with rotating proxies (out of scope for free tier).

**Result**: 3 web pages + 2 PDFs successfully ingested.
~361k chars of raw content covering all required KB categories.

**Production improvement**: Use a residential proxy pool or official
Star Health data partnership for production ingestion. Schedule weekly
re-crawl with checksum-based change detection.
