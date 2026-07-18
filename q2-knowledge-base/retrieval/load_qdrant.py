"""
Load KB records and BGE-M3 embeddings into Qdrant.

Run once after embedding step:
    python -m retrieval.load_qdrant

Collection: star_health_kb
Vector size: 1024 (BGE-M3 dense)
Distance: Cosine
"""

import json
import sys
from pathlib import Path

import numpy as np
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# ── Config ────────────────────────────────────────────────────────────────────

QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "star_health_kb"
VECTOR_SIZE = 1024
BATCH_SIZE = 64

PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
EMBEDDINGS_FILE = PROCESSED_DIR / "embeddings.npy"
RECORD_IDS_FILE = PROCESSED_DIR / "record_ids.json"
RECORDS_FILE = PROCESSED_DIR / "kb_records_with_ids.jsonl"


# ── Helpers ───────────────────────────────────────────────────────────────────


def load_data():
    embeddings = np.load(EMBEDDINGS_FILE)
    with open(RECORD_IDS_FILE, encoding="utf-8") as f:
        record_ids = json.load(f)
    records = {}
    with open(RECORDS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                records[r["record_id"]] = r
    assert len(record_ids) == embeddings.shape[0], "Mismatch between IDs and embeddings"
    logger.info(
        f"Loaded {len(record_ids)} records and embeddings shape {embeddings.shape}"
    )
    return embeddings, record_ids, records


def create_collection(client: QdrantClient):
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        logger.info(
            f"Collection '{COLLECTION_NAME}' already exists — deleting and recreating"
        )
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )
    logger.info(f"Created collection '{COLLECTION_NAME}'")


def build_payload(record: dict) -> dict:
    """Extract metadata fields for Qdrant payload (everything except content)."""
    return {
        "record_id": record.get("record_id", ""),
        "title": record.get("title", ""),
        "content": record.get("content", ""),
        "content_type": record.get("content_type", ""),
        "category": record.get("category", ""),
        "product": record.get("product", ""),
        "language": record.get("language", "en"),
        "source_url": record.get("source_url", ""),
        "source_document_id": record.get("source_document_id", ""),
        "source_document_title": record.get("source_document_title", ""),
        "section_heading": record.get("section_heading", ""),
        "chunk_index": record.get("chunk_index", 0),
        "chunk_total": record.get("chunk_total", 1),
        "version": record.get("version", ""),
        "has_pii": record.get("has_pii", False),
        "verbatim_required": record.get("verbatim_required", False),
    }


def upload_points(
    client: QdrantClient, embeddings: np.ndarray, record_ids: list, records: dict
):
    total = len(record_ids)
    uploaded = 0

    for i in range(0, total, BATCH_SIZE):
        batch_ids = record_ids[i : i + BATCH_SIZE]
        batch_embeddings = embeddings[i : i + BATCH_SIZE]

        points = []
        for j, (rid, emb) in enumerate(zip(batch_ids, batch_embeddings)):
            record = records.get(rid, {})
            points.append(
                PointStruct(
                    id=i + j,
                    vector=emb.tolist(),
                    payload=build_payload(record),
                )
            )

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        uploaded += len(points)
        logger.info(f"  Uploaded {uploaded}/{total} points")

    logger.info(f"Upload complete — {uploaded} points in '{COLLECTION_NAME}'")


def verify_collection(client: QdrantClient):
    info = client.get_collection(COLLECTION_NAME)
    count = client.count(COLLECTION_NAME).count
    logger.info(f"Collection info: {count} points, status={info.status}")

    # Quick test search using new API
    sample_vec = np.random.randn(VECTOR_SIZE).astype(np.float32)
    sample_vec = sample_vec / np.linalg.norm(sample_vec)
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=sample_vec.tolist(),
        limit=3,
    ).points
    logger.info(f"Test search returned {len(results)} results")
    for r in results:
        logger.info(
            f"  [{r.score:.4f}] {r.payload.get('record_id')} — {r.payload.get('title', '')[:50]}"
        )


def main():
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}",
        level="INFO",
    )

    logger.info("=" * 60)
    logger.info("Loading KB into Qdrant")
    logger.info("=" * 60)

    client = QdrantClient(url=QDRANT_URL, check_compatibility=False)
    embeddings, record_ids, records = load_data()
    create_collection(client)
    upload_points(client, embeddings, record_ids, records)
    verify_collection(client)
    logger.info("Done. Qdrant collection ready.")


if __name__ == "__main__":
    main()
