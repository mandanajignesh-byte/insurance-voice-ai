# Knowledge Base Schema

This document defines the record structure, taxonomy, chunking rules, versioning model,
PII handling, multilingual strategy, and citation format for the AI Assessment knowledge base.
Every ingestion, processing, retrieval, and agent step must conform to this schema.

---

## 1. Source Overview

Three insurance/finance companies anchor the three voice agent use cases:

| Source | Domain | Language | Used by |
|---|---|---|---|
| Star Health India | Health insurance renewal | English | Q1 voice agent |
| Sun Life Philippines | Life insurance renewal | Filipino / Taglish / English | Q3-PH agent |
| Adira Finance Indonesia | Multifinance installment reminder | Bahasa Indonesia / English | Q3-ID agent |

All three sources use the same record schema and are stored in the same Qdrant collection,
distinguished by the `language` and `source_document_id` fields.

---

## 2. Record Schema

Every record in the knowledge base is a JSON object with the following fields.
All fields are required unless marked optional.

```json
{
  "record_id":             "kb_star_prod_001_c003",
  "title":                 "Family Health Optima — Room Rent Coverage",
  "content":               "The plan covers room rent up to 2% of sum insured per day...",
  "content_type":          "chunk",
  "category":              "product_coverage",
  "product":               "family_health_optima",
  "language":              "en",
  "source_url":            "https://www.starhealth.in/health-insurance/family-health-optima/",
  "source_document_id":    "kb_star_prod_001",
  "source_document_title": "Family Health Optima — Product Brochure",
  "section_heading":       "Coverage Benefits",
  "chunk_index":           3,
  "chunk_total":           12,
  "page_number":           null,
  "version":               "2026.07",
  "superseded_by":         null,
  "ingested_at":           "2026-07-18T10:00:00Z",
  "extraction_status":     "clean",
  "has_pii":               false,
  "pii_types":             [],
  "terminology_normalized": true,
  "checksum":              "sha256:abc123def456..."
}
```

### 2.1 Field definitions

| Field | Type | Description |
|---|---|---|
| `record_id` | string | Unique identifier. Format: `kb_{source}_{category_short}_{doc_seq}_c{chunk_seq}`. For atomic records (no chunking), omit `_c{chunk_seq}`. Examples: `kb_star_faq_007`, `kb_sunlife_prod_002_c004`. |
| `title` | string | Human-readable title. For chunks: parent document title + section heading. For atomics: the FAQ question or objection phrase. |
| `content` | string | The actual text that gets embedded and retrieved. Clean, normalized prose. No HTML, no navigation text, no headers repeated inside the content. |
| `content_type` | enum | `chunk` — a piece of a larger document. `atomic` — a self-contained unit (FAQ, objection, disclosure, rule). `summary` — LLM-generated summary of a long document for coarse retrieval. |
| `category` | enum | See Section 3. Exactly one value per record. |
| `product` | string | Slug of the product or service this record describes. Examples: `family_health_optima`, `star_comprehensive`. Empty string `""` if the record applies to the company generally rather than a specific product. |
| `language` | enum | `en` (English), `fil` (Filipino/Tagalog/Taglish), `id` (Bahasa Indonesia). |
| `source_url` | string | The exact URL of the web page or PDF this content was extracted from. Must be a valid URL. For PDFs use the direct PDF URL. |
| `source_document_id` | string | The parent document identifier, shared by all chunks from the same source document. Format: `kb_{source}_{category_short}_{doc_seq}`. |
| `source_document_title` | string | Human-readable title of the parent document (e.g., "Family Health Optima — Product Brochure", "Star Health FAQ Page"). |
| `section_heading` | string | The H2 or H3 heading under which this chunk appears. Empty string if the source has no headings. |
| `chunk_index` | integer | 0-based position of this chunk within its parent document. For atomic records: always `0`. |
| `chunk_total` | integer | Total number of chunks the parent document produced. For atomic records: always `1`. |
| `page_number` | integer or null | PDF page number this content was extracted from. `null` for web pages. |
| `version` | string | Ingestion version in `YYYY.MM` format, tied to when the source was crawled. Example: `"2026.07"`. |
| `superseded_by` | string or null | If this record has been replaced by a newer version, contains the `record_id` of the replacement. `null` if this is the current active record. |
| `ingested_at` | string | ISO 8601 UTC timestamp of when this record was created. |
| `extraction_status` | enum | `clean` — extraction was complete and confident. `partial` — some content may be missing (e.g., table not fully parsed). `failed` — extraction failed; record is a stub. |
| `has_pii` | boolean | `true` if the original content contained PII that was redacted. The stored `content` field already has PII replaced with tokens. |
| `pii_types` | array of strings | Which PII types were found and redacted. Values from: `email`, `phone`, `aadhaar`, `pan`, `policy_number`, `dob`, `name`, `address`. Empty array if `has_pii` is false. |
| `terminology_normalized` | boolean | `true` if the terminology normalization pass ran on this record. |
| `checksum` | string | SHA-256 hash of the raw extracted content before cleaning. Used to detect whether a re-crawl changed the source content. Format: `sha256:{hex}`. |

---

## 3. Category Taxonomy

Every record belongs to exactly one category. The controlled vocabulary is:

| Category value | What it covers | Content type | Example |
|---|---|---|---|
| `product_overview` | High-level description of a product — what it is, who it is for | chunk | "Family Health Optima is a floater plan covering the entire family under one sum insured..." |
| `product_coverage` | What is covered — benefits, inclusions, sublimits | chunk | "Room rent is covered up to 2% of sum insured per day..." |
| `product_exclusions` | What is not covered — exclusions, waiting periods for specific conditions | chunk | "Cosmetic treatments, dental procedures unless arising from accident, and obesity treatments are excluded..." |
| `product_pricing` | Premium tables, sum insured options, discount structures | chunk | "For a family of four, the annual premium for Rs. 10 lakh sum insured starts at Rs. 18,200..." |
| `qualification_rule` | Eligibility criteria — age bands, medical declarations, pre-existing disease handling, waiting periods | atomic | "Entry age: 18–65 years for primary insured. Children: 91 days to 25 years. No medical check-up required up to age 45 for sum insured up to Rs. 15 lakh." |
| `policy_terms` | Renewal clauses, grace period, cancellation, portability, co-payment | chunk | "The policy offers a 30-day grace period for renewal. Portability to another insurer is permitted as per IRDAI guidelines..." |
| `claim_process` | How to file a claim, documents needed, cashless vs reimbursement, timelines | chunk | "For planned hospitalization, intimate the insurer at least 48 hours in advance. For emergencies, notify within 24 hours of admission..." |
| `faq` | Atomic Q/A pairs — one question and its answer | atomic | Q: "Can I add a newborn to my policy?" A: "Yes, newborns can be added within 90 days of birth without waiting period..." |
| `objection_response` | Pre-authored responses to common customer objections | atomic | Objection: "The premium is too expensive." Response: "I understand the concern — the plan actually averages Rs. X per day per family member, which includes Y and Z benefits..." |
| `disclosure` | Mandatory regulatory disclosures the agent must read aloud at specific points | atomic | "This is an insurance product. Please read all terms and conditions carefully before purchasing. Premiums are subject to change at renewal." |
| `contact_escalation` | How to reach a human agent, branch office, grievance redressal | atomic | "To speak with a relationship manager, call 1800-425-2255 (toll-free, Monday–Saturday, 8 AM to 8 PM)." |

### Category assignment rules

- When content could fit two categories, assign the more specific one. "Waiting period for pre-existing diseases" → `qualification_rule`, not `policy_terms`.
- `objection_response` records are authored manually by reviewing customer complaints, reviews, and common call center patterns. They are not scraped directly from the source website.
- `disclosure` records must be flagged for exact wording — the agent must read them verbatim, not paraphrase. Add a boolean field `verbatim_required: true` only on `disclosure` records.

---

## 4. Chunking Rules

### 4.1 Atomic categories (no chunking)

The following categories are always stored as a single record regardless of length:

- `faq`
- `objection_response`
- `disclosure`
- `qualification_rule`
- `contact_escalation`

For these: `chunk_index = 0`, `chunk_total = 1`, `content_type = "atomic"`.

### 4.2 Chunked categories

The following categories are chunked from their source documents:

- `product_overview`
- `product_coverage`
- `product_exclusions`
- `product_pricing`
- `policy_terms`
- `claim_process`

**Chunking strategy (apply in order):**

1. **Structural split first**: split on H2 and H3 headings. Each section becomes a candidate chunk.
2. **Token check**: if a section is ≤ 500 tokens, it is one chunk.
3. **Semantic split for long sections**: if a section is > 500 tokens, split further at natural paragraph or sentence boundaries, targeting 300–400 tokens per chunk. Never split mid-sentence.
4. **Overlap**: adjacent chunks from the same section share a 50-token overlap (the last 50 tokens of chunk N are the first 50 tokens of chunk N+1). This preserves context at boundaries.
5. **Minimum size**: chunks shorter than 50 tokens are merged into the next chunk. A chunk of just a heading is discarded.

**Token counting**: use the `tiktoken` library with the `cl100k_base` encoding (same tokenizer as GPT-4, close enough to BGE-M3 for size estimation purposes).

### 4.3 Summary records

For any source document longer than 2,000 tokens total, generate one additional `summary` record:
- `content_type = "summary"`
- `chunk_index = -1` (sentinel value, not a real chunk)
- `content` = LLM-generated 150-word summary of the full document
- `category` = same as the document's primary category
- Purpose: handles high-level queries ("tell me about Family Health Optima") without retrieving a specific chunk

---

## 5. Source Tracking

Every record must have a fully populated `source_url` and `source_document_title`.

When a chunk is retrieved and used in an agent response, the citation is constructed as:
[{record_id}] {source_document_title}, section "{section_heading}"

Example:
[kb_star_cov_002_c003] Family Health Optima Product Brochure, section "Coverage Benefits"

This citation is:
- Written to the call log alongside every agent response
- Included in the retrieval API response so the calling service can log it
- Available for the video walkthrough to demonstrate grounded answers

For atomic records with no section heading, the citation is:
[{record_id}] {source_document_title}

---

## 6. Versioning Model

### 6.1 Version string

Format: `YYYY.MM` — year and month of the ingestion run.
Example: first ingestion in July 2026 → `"2026.07"`.

### 6.2 Re-ingestion behavior

When a re-ingestion run processes a source URL:

1. Compute the SHA-256 checksum of the newly extracted raw content.
2. Compare against the `checksum` of existing records for that `source_document_id`.
3. **If checksums match**: content has not changed. Skip. Do not create new records.
4. **If checksums differ**: content has changed.
   - Create new records with the new `version` string.
   - For each new record, set the corresponding old record's `superseded_by` to the new `record_id`.
   - Old records remain in the database — they are not deleted.

### 6.3 Retrieval filter

All retrieval queries filter on `superseded_by IS NULL` (Qdrant: `must_not` condition on `superseded_by` field being non-null). Only current records are retrieved by default.

### 6.4 Audit use

Old (superseded) records can be queried explicitly by version string. This allows answering "what did the policy say in July 2026?" — useful for compliance audits and for the demo.

---

## 7. PII Handling

### 7.1 Detection

Run Microsoft Presidio with the following recognizers enabled:

- Built-in: `EMAIL_ADDRESS`, `PHONE_NUMBER`, `DATE_TIME`, `PERSON`, `LOCATION`
- Custom (Indian context): `AADHAAR_NUMBER` (12-digit pattern), `PAN_NUMBER` (ABCDE1234F pattern), `POLICY_NUMBER` (alphanumeric 8–16 chars matching insurer prefix patterns)

### 7.2 Redaction

Replace detected PII with typed tokens before storing in `content`:

| PII type | Replacement token |
|---|---|
| Email | `<EMAIL>` |
| Phone | `<PHONE>` |
| Aadhaar | `<AADHAAR>` |
| PAN | `<PAN>` |
| Policy number | `<POLICY_NUMBER>` |
| Date of birth | `<DOB>` |
| Person name | `<NAME>` |
| Address | `<ADDRESS>` |

The original content is never stored anywhere in the pipeline. Redaction happens in the processing step before records are written to disk or loaded into Qdrant.

### 7.3 Record flags

Set `has_pii = true` and populate `pii_types` with the list of PII types that were found and redacted.

For our source material (public marketing pages), PII will be rare. The pipeline handles it consistently so it is production-safe.

---

## 8. Multilingual Strategy

### 8.1 Language field

Every record carries a `language` field with one of: `en`, `fil`, `id`.

### 8.2 Retrieval by language

| Agent | Query filter |
|---|---|
| Q1 (English) | `language = "en"` |
| Q3-PH (Filipino) | `language IN ["fil", "en"]` |
| Q3-ID (Indonesian) | `language IN ["id", "en"]` |

### 8.3 Authoring rule

Filipino (`fil`) and Indonesian (`id`) records are **authored in the target language**, not translated from English. They represent the natural way a local agent in that market would explain the product, handle an objection, or read a disclosure.

A Filipino objection response is written as Taglish if that is how a Manila-based bancassurance agent would actually say it. An Indonesian installment reminder is written in the register a collections agent in Surabaya would use — not formal Jakarta corporate Bahasa.

This is a hard rule. Literal English-to-Filipino or English-to-Indonesian translation is not acceptable. If the source content only exists in English, the record is stored as `language = "en"` and is accessible to all agents. Localized content is added as a separate record with `language = "fil"` or `language = "id"`.

### 8.4 Embedding

BGE-M3 is used for all embeddings. It supports English, Filipino, and Bahasa Indonesia in the same vector space, so a single Qdrant collection holds all three languages and cross-lingual retrieval is possible without any special handling.

---

## 9. Document Manifest

Alongside `kb_records.jsonl` (one JSON object per line, one line per chunk/atomic), maintain a `kb_documents.jsonl` file with one entry per source document:

```json
{
  "source_document_id": "kb_star_prod_001",
  "source_document_title": "Family Health Optima — Product Brochure",
  "source_url": "https://www.starhealth.in/...",
  "language": "en",
  "version": "2026.07",
  "ingested_at": "2026-07-18T10:00:00Z",
  "extraction_status": "clean",
  "total_chunks": 12,
  "chunk_ids": [
    "kb_star_prod_001_c000",
    "kb_star_prod_001_c001",
    "...etc"
  ],
  "summary_record_id": "kb_star_prod_001_summary",
  "checksum": "sha256:abc123..."
}
```

The document manifest is used for:
- Re-ingestion checksum comparison
- Context expansion (retrieve sibling chunks when one chunk is not enough)
- Version tracking and audit

---

## 10. Terminology Normalization

Before storing content, apply a normalization pass that maps synonym variants to a canonical term.
The alias map is stored in `q2-knowledge-base/processing/terminology_aliases.json`.

Initial alias map (to be expanded during ingestion):

```json
{
  "sum insured":        ["coverage amount", "insured amount", "sum assured", "si"],
  "premium":            ["policy premium", "insurance premium", "annual premium"],
  "pre-existing":       ["pre existing", "pre-existing disease", "ped", "prior condition"],
  "cashless":           ["cashless claim", "cashless treatment", "direct billing"],
  "co-payment":         ["co-pay", "copayment", "copay"],
  "waiting period":     ["waiting time", "exclusion period"],
  "grace period":       ["grace days", "renewal grace"],
  "renewal":            ["policy renewal", "renew policy"]
}
```

All terms in each list are normalized to the canonical key (first element of each key-value pair — the key itself). Normalization is case-insensitive.

Set `terminology_normalized = true` on the record after this pass runs.

---

## 11. Worked Examples

### Example 1 — Chunk record (product coverage)

```json
{
  "record_id": "kb_star_cov_002_c001",
  "title": "Family Health Optima — Day Care Treatment Coverage",
  "content": "The plan covers over 500 day care treatments that do not require 24-hour hospitalization. These include procedures such as dialysis, chemotherapy, radiotherapy, lithotripsy, and cataract surgery. Each day care treatment is covered up to the sum insured limit without a separate sublimit.",
  "content_type": "chunk",
  "category": "product_coverage",
  "product": "family_health_optima",
  "language": "en",
  "source_url": "https://www.starhealth.in/health-insurance/family-health-optima/",
  "source_document_id": "kb_star_cov_002",
  "source_document_title": "Family Health Optima — Coverage Details",
  "section_heading": "Day Care Treatment",
  "chunk_index": 1,
  "chunk_total": 8,
  "page_number": null,
  "version": "2026.07",
  "superseded_by": null,
  "ingested_at": "2026-07-18T10:00:00Z",
  "extraction_status": "clean",
  "has_pii": false,
  "pii_types": [],
  "terminology_normalized": true,
  "checksum": "sha256:3f7a91b2..."
}
```

### Example 2 — Atomic record (FAQ)

```json
{
  "record_id": "kb_star_faq_007",
  "title": "Can I add a newborn to my existing Family Health Optima policy?",
  "content": "Yes. A newborn can be added to the policy within 90 days of birth without any waiting period. Contact the insurer or your agent to endorse the addition. The premium will be adjusted pro-rata for the remaining policy term.",
  "content_type": "atomic",
  "category": "faq",
  "product": "family_health_optima",
  "language": "en",
  "source_url": "https://www.starhealth.in/faq/",
  "source_document_id": "kb_star_faq_000",
  "source_document_title": "Star Health FAQ Page",
  "section_heading": "Policy Changes",
  "chunk_index": 0,
  "chunk_total": 1,
  "page_number": null,
  "version": "2026.07",
  "superseded_by": null,
  "ingested_at": "2026-07-18T10:00:00Z",
  "extraction_status": "clean",
  "has_pii": false,
  "pii_types": [],
  "terminology_normalized": true,
  "checksum": "sha256:9c2e44f1..."
}
```

### Example 3 — Atomic record (objection response, Filipino)

```json
{
  "record_id": "kb_sunlife_obj_003",
  "title": "Objection: Premium is too expensive",
  "content": "Naiintindihan ko po ang concern niyo sa premium. Pero kung titingnan natin, halos dalawang piso lang po bawat araw ang katumbas nito para sa buong family niyo. At kasama na po doon ang coverage para sa critical illness at hospital confinement. Mas mahal pa po ang hindi magkaroon ng proteksyon kapag kailangan na.",
  "content_type": "atomic",
  "category": "objection_response",
  "product": "sun_life_flexi_life_protect",
  "language": "fil",
  "source_url": "",
  "source_document_id": "kb_sunlife_obj_000",
  "source_document_title": "Sun Life PH — Authored Objection Responses",
  "section_heading": "Premium Objections",
  "chunk_index": 0,
  "chunk_total": 1,
  "page_number": null,
  "version": "2026.07",
  "superseded_by": null,
  "ingested_at": "2026-07-18T10:00:00Z",
  "extraction_status": "clean",
  "has_pii": false,
  "pii_types": [],
  "terminology_normalized": true,
  "checksum": "sha256:1d8f7c3a..."
}
```

### Example 4 — Atomic record (disclosure, verbatim required)

```json
{
  "record_id": "kb_star_disc_001",
  "title": "IRDAI Mandatory Insurance Disclosure",
  "content": "This is an insurance product regulated by the Insurance Regulatory and Development Authority of India. Please read the policy terms and conditions carefully before purchasing. Past performance of any product is not indicative of future results. Premium is subject to revision at renewal.",
  "content_type": "atomic",
  "category": "disclosure",
  "product": "",
  "language": "en",
  "verbatim_required": true,
  "source_url": "https://www.starhealth.in/terms/",
  "source_document_id": "kb_star_disc_000",
  "source_document_title": "Star Health — Regulatory Disclosures",
  "section_heading": "",
  "chunk_index": 0,
  "chunk_total": 1,
  "page_number": null,
  "version": "2026.07",
  "superseded_by": null,
  "ingested_at": "2026-07-18T10:00:00Z",
  "extraction_status": "clean",
  "has_pii": false,
  "pii_types": [],
  "terminology_normalized": true,
  "checksum": "sha256:6b4e2091..."
}
```

---

## 12. What this schema does NOT include

Being explicit about scope helps reviewers understand the design is deliberate:

- **No vector field in the schema** — embeddings live in Qdrant, not in the JSONL files. The JSONL is the source of truth; Qdrant is the index.
- **No full document text stored** — only chunks and atomic records. Full text is in the raw data directory, gitignored.
- **No agent conversation history** — that is managed by the voice agent, not the KB.
- **No user data** — the KB is read-only content. No customer records, no call logs.

---

*Schema version: 1.0 — July 2026*
*Owner: Q2 knowledge base pipeline*
*Next review: on first re-ingestion run or when a new source is added*
