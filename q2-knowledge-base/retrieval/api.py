"""
FastAPI retrieval service.

Exposes the KB search as an HTTP API consumed by:
- Q1 voice agent (tool call)
- Q3 localized agents
- Q2 evaluation harness

Run:
    python -m retrieval.api

Endpoints:
    POST /search        — main search endpoint
    GET  /health        — health check
    GET  /stats         — collection stats
"""

import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from retrieval.search import search_kb, format_for_agent

app = FastAPI(
    title="Star Health KB Retrieval API",
    description="Knowledge base search for Star Health insurance products",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ─────────────────────────────────────────────────


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    language: str = "en"
    category_filter: Optional[str] = None
    score_threshold: float = 0.3
    format_for_agent: bool = True


class SearchResultItem(BaseModel):
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


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem]
    result_count: int
    formatted_context: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok", "service": "kb-retrieval"}


@app.get("/stats")
def stats():
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url="http://localhost:6333", check_compatibility=False)
        info = client.get_collection("star_health_kb")
        count = client.count("star_health_kb").count
        return {
            "collection": "star_health_kb",
            "points": count,
            "status": str(info.status),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search", response_model=SearchResponse)
def search(request: SearchRequest):
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        results = search_kb(
            query=request.query,
            top_k=request.top_k,
            language=request.language,
            category_filter=request.category_filter,
            score_threshold=request.score_threshold,
        )

        items = [
            SearchResultItem(
                record_id=r.record_id,
                title=r.title,
                content=r.content,
                category=r.category,
                product=r.product,
                source_document_title=r.source_document_title,
                section_heading=r.section_heading,
                source_url=r.source_url,
                score=r.score,
                verbatim_required=r.verbatim_required,
                citation=r.citation,
            )
            for r in results
        ]

        formatted = None
        if request.format_for_agent:
            formatted = format_for_agent(results)

        return SearchResponse(
            query=request.query,
            results=items,
            result_count=len(items),
            formatted_context=formatted,
        )

    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("retrieval.api:app", host="0.0.0.0", port=8000, reload=False)
