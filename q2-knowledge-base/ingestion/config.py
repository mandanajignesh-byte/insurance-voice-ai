"""
Ingestion configuration.
Defines target URLs, PDF sources, crawl settings, and output paths.
All paths are relative to the repo root.
"""

from pathlib import Path

# ── Repo layout ────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "q2-knowledge-base" / "data" / "raw"
SAMPLES_DIR = REPO_ROOT / "q2-knowledge-base" / "data" / "samples"

# ── Star Health — web pages to crawl ──────────────────────────────────────────
# These are public marketing and product pages.
# We crawl each URL individually (not a full site crawl) to stay within
# Firecrawl's free tier (500 pages/month) and avoid irrelevant pages.

STAR_HEALTH_WEB_TARGETS = [
    {
        "url": "https://www.starhealth.in/health-insurance/family-health-optima/",
        "category": "product_overview",
        "product": "family_health_optima",
        "doc_id": "kb_star_web_001",
        "title": "Family Health Optima — Product Page",
    },
    {
        "url": "https://www.starhealth.in/health-insurance/star-comprehensive-insurance-policy/",
        "category": "product_overview",
        "product": "star_comprehensive",
        "doc_id": "kb_star_web_002",
        "title": "Star Comprehensive Insurance Policy — Product Page",
    },
    {
        "url": "https://www.starhealth.in/health-insurance/young-star-insurance-policy/",
        "category": "product_overview",
        "product": "young_star",
        "doc_id": "kb_star_web_003",
        "title": "Young Star Insurance Policy — Product Page",
    },
    {
        "url": "https://www.starhealth.in/health-insurance/senior-citizens-red-carpet/",
        "category": "product_overview",
        "product": "senior_citizens_red_carpet",
        "doc_id": "kb_star_web_004",
        "title": "Senior Citizens Red Carpet Health Insurance — Product Page",
    },
    {
        "url": "https://www.starhealth.in/frequently-asked-questions/",
        "category": "faq",
        "product": "",
        "doc_id": "kb_star_web_005",
        "title": "Star Health — Frequently Asked Questions",
    },
    {
        "url": "https://www.starhealth.in/health-insurance/",
        "category": "product_overview",
        "product": "",
        "doc_id": "kb_star_web_006",
        "title": "Star Health — Health Insurance Overview",
    },
    {
        "url": "https://www.starhealth.in/claim-process/",
        "category": "claim_process",
        "product": "",
        "doc_id": "kb_star_web_007",
        "title": "Star Health — Claim Process",
    },
    {
        "url": "https://www.starhealth.in/health-insurance/family-health-optima/benefits/",
        "category": "product_coverage",
        "product": "family_health_optima",
        "doc_id": "kb_star_web_008",
        "title": "Family Health Optima — Benefits",
    },
    {
        "url": "https://www.starhealth.in/renewal/",
        "category": "policy_terms",
        "product": "",
        "doc_id": "kb_star_web_009",
        "title": "Star Health — Policy Renewal",
    },
    {
        "url": "https://www.starhealth.in/contact-us/",
        "category": "contact_escalation",
        "product": "",
        "doc_id": "kb_star_web_010",
        "title": "Star Health — Contact Us",
    },
]

# ── Star Health — PDF brochures (remote download) ─────────────────────────────
# Keeping empty — starhealth.in blocks programmatic downloads.
# PDFs are downloaded manually and parsed via LOCAL_PDF_TARGETS below.

STAR_HEALTH_PDF_TARGETS = []

# ── Star Health — PDF brochures (local files, manually downloaded) ────────────
# CDN URLs work in browser but we parse from local copies for reliability.

LOCAL_PDF_TARGETS = [
    {
        "file_path": str(
            RAW_DIR
            / "pdfs"
            / "Brochure_Family_Health_Optima_Insurance_Plan_V_15_Web_74cee1b82f.pdf"
        ),
        "source_url": "https://d28c6jni2fmamz.cloudfront.net/Brochure_Family_Health_Optima_Insurance_Plan_V_15_Web_74cee1b82f.pdf",
        "category": "product_coverage",
        "product": "family_health_optima",
        "doc_id": "kb_star_pdf_001",
        "title": "Family Health Optima — Product Brochure (PDF)",
    },
    {
        "file_path": str(
            RAW_DIR
            / "pdfs"
            / "Policy_Family_Health_Optima_Insurance_Plan_V_21_bbe089bd74.pdf"
        ),
        "source_url": "https://d28c6jni2fmamz.cloudfront.net/Policy_Family_Health_Optima_Insurance_Plan_V_21_bbe089bd74.pdf",
        "category": "policy_terms",
        "product": "family_health_optima",
        "doc_id": "kb_star_pdf_002",
        "title": "Family Health Optima — Policy Clause Document (PDF)",
    },
]

# ── Output settings ────────────────────────────────────────────────────────────

WEB_RAW_FILE = RAW_DIR / "star_health_web_raw.jsonl"
PDF_RAW_FILE = RAW_DIR / "star_health_pdf_raw.jsonl"
LOCAL_PDF_RAW_FILE = RAW_DIR / "star_health_local_pdf_raw.jsonl"
CRAWL_MANIFEST_FILE = RAW_DIR / "crawl_manifest.json"


# ── Crawl settings ─────────────────────────────────────────────────────────────

CRAWL_TIMEOUT_SECONDS = 30
CRAWL_RETRY_ATTEMPTS = 3
CRAWL_RETRY_WAIT_SECONDS = 2
MIN_CONTENT_LENGTH = 200  # Discard pages with fewer than 200 chars of text

# ── Output settings ────────────────────────────────────────────────────────────

WEB_RAW_FILE = RAW_DIR / "star_health_web_raw.jsonl"
PDF_RAW_FILE = RAW_DIR / "star_health_pdf_raw.jsonl"
CRAWL_MANIFEST_FILE = RAW_DIR / "crawl_manifest.json"
