"""
Retrieval API — search the Qdrant KB collection.

Used by:
- Q1 voice agent (FastAPI tool call)
- Q2 evaluation harness
- Q3 localized agents

Usage:
    from retrieval.search import search_kb
    results = search_kb("what is the waiting period for pre-existing diseases")
"""

import sys
from pathlib import Path
from dataclasses import dataclass

import numpy as np
from loguru import logger
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "star_health_kb"
VECTOR_SIZE = 1024

# Lazy-loaded model
_model = None
_client = None


def _get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=QDRANT_URL, check_compatibility=False)
    return _client


def _get_model():
    global _model
    if _model is None:
        from FlagEmbedding import BGEM3FlagModel

        logger.info("Loading BGE-M3 model...")
        _model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
        logger.info("BGE-M3 ready")
    return _model


@dataclass
class SearchResult:
    record_id: str
    title: str
    content: str
    category: str
    product: str
    source_document_title: str
    section_heading: str
    source_url: str
    score: float
    verbatim_required: bool
    citation: str


def search_kb(
    query: str,
    top_k: int = 5,
    language: str = "en",
    category_filter: str = None,
    score_threshold: float = 0.3,
) -> list[SearchResult]:
    """
    Search the KB for relevant records.

    Args:
        query: Natural language query
        top_k: Number of results to return
        language: Filter by language ("en", "fil", "id")
        category_filter: Optional single category to filter by
        score_threshold: Minimum cosine similarity score

    Returns:
        List of SearchResult objects sorted by score descending
    """
    model = _get_model()
    client = _get_client()

    # Embed query
    output = model.encode(
        [query],
        batch_size=1,
        max_length=256,
        return_dense=True,
        return_sparse=False,
        return_colbert_vecs=False,
    )
    query_vector = output["dense_vecs"][0].tolist()

    # Build filters
    must_conditions = []

    # Language filter
    if language == "en":
        must_conditions.append(
            FieldCondition(key="language", match=MatchValue(value="en"))
        )
    elif language == "fil":
        must_conditions.append(
            FieldCondition(key="language", match=MatchAny(any=["fil", "en"]))
        )
    elif language == "id":
        must_conditions.append(
            FieldCondition(key="language", match=MatchAny(any=["id", "en"]))
        )

    # Category filter
    if category_filter:
        must_conditions.append(
            FieldCondition(key="category", match=MatchValue(value=category_filter))
        )

    # Exclude superseded records (verbatim_required or version check)
    qdrant_filter = Filter(must=must_conditions) if must_conditions else None

    # Search
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        query_filter=qdrant_filter,
        score_threshold=score_threshold,
        with_payload=True,
    ).points

    # Build results
    search_results = []
    for r in results:
        p = r.payload
        section = p.get("section_heading", "")
        doc_title = p.get("source_document_title", "")
        record_id = p.get("record_id", "")

        citation = f"[{record_id}] {doc_title}"
        if section:
            citation += f', section "{section}"'

        search_results.append(
            SearchResult(
                record_id=record_id,
                title=p.get("title", ""),
                content=p.get("content", ""),
                category=p.get("category", ""),
                product=p.get("product", ""),
                source_document_title=doc_title,
                section_heading=section,
                source_url=p.get("source_url", ""),
                score=r.score,
                verbatim_required=p.get("verbatim_required", False),
                citation=citation,
            )
        )

    return search_results


def format_for_agent(results: list[SearchResult]) -> str:
    """
    Format search results as a context string for the voice agent LLM.
    Includes citations so the agent can reference sources.
    """
    if not results:
        return "No relevant information found in the knowledge base."

    lines = ["RETRIEVED KNOWLEDGE BASE CONTEXT:", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r.citation}")
        lines.append(f"Score: {r.score:.3f} | Category: {r.category}")
        if r.verbatim_required:
            lines.append("⚠ VERBATIM REQUIRED — read this exactly as written")
        lines.append(f"Content: {r.content}")
        lines.append("")

    return "\n".join(lines)
