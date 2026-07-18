"""
Ingestion pipeline entry point.

Usage:
    python -m ingestion.run --mode web      # crawl web pages only
    python -m ingestion.run --mode pdf      # parse PDFs only
    python -m ingestion.run --mode all      # both (default)

Output files (in q2-knowledge-base/data/raw/):
    star_health_web_raw.jsonl   — one RawDocument per line (web)
    star_health_pdf_raw.jsonl   — one RawDocument per line (PDF)
    crawl_manifest.json         — summary of this run
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Add repo root to path so `ingestion` package resolves correctly
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingestion import config as cfg
from ingestion.crawl_web import crawl_all_web_targets
from ingestion.parse_pdf import parse_all_pdf_targets
from ingestion.models import RawDocument, ExtractionStatus
from ingestion.utils import ensure_dir, log_separator, utc_now_iso

load_dotenv()


# ── Logging setup ─────────────────────────────────────────────────────────────

logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
    level="INFO",
)
logger.add(
    cfg.RAW_DIR / "ingestion.log",
    rotation="10 MB",
    level="DEBUG",
)


# ── Save helpers ──────────────────────────────────────────────────────────────


def save_jsonl(docs: list[RawDocument], output_path: Path) -> None:
    """Save a list of RawDocument objects as JSONL."""
    ensure_dir(output_path.parent)
    with open(output_path, "w", encoding="utf-8") as f:
        for doc in docs:
            f.write(doc.model_dump_json() + "\n")
    logger.info(f"Saved {len(docs)} records → {output_path}")


def build_manifest(
    web_docs: list[RawDocument],
    pdf_docs: list[RawDocument],
    run_start: str,
    run_end: str,
) -> dict:
    """Build a summary manifest of the crawl run."""
    all_docs = web_docs + pdf_docs

    def count_status(docs, status):
        return sum(1 for d in docs if d.extraction_status == status)

    return {
        "run_start": run_start,
        "run_end": run_end,
        "version": datetime.now(timezone.utc).strftime("%Y.%m"),
        "summary": {
            "total_documents": len(all_docs),
            "web_documents": len(web_docs),
            "pdf_documents": len(pdf_docs),
            "successful": count_status(all_docs, "success"),
            "partial": count_status(all_docs, "partial"),
            "failed": count_status(all_docs, "failed"),
            "total_chars_extracted": sum(d.char_count for d in all_docs),
        },
        "web_results": [
            {
                "doc_id": d.doc_id,
                "url": d.source_url,
                "status": d.extraction_status,
                "chars": d.char_count,
                "crawler": d.crawler_used,
                "error": d.extraction_error,
            }
            for d in web_docs
        ],
        "pdf_results": [
            {
                "doc_id": d.doc_id,
                "url": d.source_url,
                "status": d.extraction_status,
                "chars": d.char_count,
                "pages": f"{d.pages_extracted}/{d.page_count}",
                "error": d.extraction_error,
            }
            for d in pdf_docs
        ],
    }


# ── Main ──────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Run the Star Health ingestion pipeline"
    )
    parser.add_argument(
        "--mode",
        choices=["web", "pdf", "local-pdf", "all"],
        default="all",
    )
    args = parser.parse_args()

    ensure_dir(cfg.RAW_DIR)
    run_start = utc_now_iso()

    log_separator("Star Health Ingestion Pipeline")
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Output directory: {cfg.RAW_DIR}")
    logger.info(f"Run start: {run_start}")

    web_docs: list[RawDocument] = []
    pdf_docs: list[RawDocument] = []

    if args.mode in ("web", "all"):
        web_docs = crawl_all_web_targets()
        save_jsonl(web_docs, cfg.WEB_RAW_FILE)

    if args.mode in ("pdf", "all"):
        pdf_docs = parse_all_pdf_targets()
        save_jsonl(pdf_docs, cfg.PDF_RAW_FILE)

    if args.mode in ("local-pdf", "all"):
        from ingestion.parse_pdf import parse_all_local_pdfs

        local_pdf_docs = parse_all_local_pdfs()
        save_jsonl(local_pdf_docs, cfg.LOCAL_PDF_RAW_FILE)

    run_end = utc_now_iso()

    # Save manifest
    all_pdf_docs = pdf_docs + (local_pdf_docs if "local_pdf_docs" in dir() else [])
    manifest = build_manifest(web_docs, all_pdf_docs, run_start, run_end)
    with open(cfg.CRAWL_MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    logger.info(f"Manifest saved → {cfg.CRAWL_MANIFEST_FILE}")

    # Print final summary
    log_separator("Summary")
    s = manifest["summary"]
    logger.info(f"Total documents : {s['total_documents']}")
    logger.info(f"Successful      : {s['successful']}")
    logger.info(f"Partial         : {s['partial']}")
    logger.info(f"Failed          : {s['failed']}")
    logger.info(f"Total chars     : {s['total_chars_extracted']:,}")

    if s["failed"] > 0:
        logger.warning(
            f"{s['failed']} document(s) failed. "
            f"Check {cfg.RAW_DIR}/ingestion.log for details."
        )
        logger.warning("Failed documents will be excluded from the KB automatically.")

    logger.info("Ingestion complete.")


if __name__ == "__main__":
    main()
