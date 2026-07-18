# AI Engineer Assessment

This repository is a four-part AI Engineer assessment submission covering a knowledge-grounded voice agent (Q1), a production-ready knowledge base (Q2), localized voice bots for the Philippines and Indonesia (Q3), and a real-time call insights pipeline (Q4). The anchor domain is insurance renewal and reminder flows, with Star Health (India) for Q1, Sun Life Philippines for Q3-PH, and Adira Finance Indonesia for Q3-ID.

## Repository layout

```text
q2-knowledge-base/        # Knowledge ingestion, processing, embedding, retrieval, and evaluation assets
  ingestion/
  processing/
  embedding/
  retrieval/
  evaluation/
  notebooks/
  data/
    raw/
    processed/
    samples/
q1-voice-agent/          # Star Health insurance renewal voice agent
  agent/
  prompts/
  tools/
  web-client/
  recordings/
q3-localized/            # Localized voice bots for the Philippines and Indonesia
  ph-agent/
  id-agent/
  kb-entries/
  recordings/
q4-realtime/             # Real-time call insights, signals, nudges, dashboard, and evaluation
  streaming/
  signals/
  nudges/
  dashboard/
  evaluation/
  notebooks/
docs/                    # Cross-project documentation, decisions, limitations, and architecture notes
```

## Architecture at a glance

- Pipecat voice framework for conversational voice agents.
- Qdrant vector DB for local vector storage.
- BGE-M3 embeddings generated offline for multilingual retrieval.
- Groq and Gemini LLMs for hosted model inference.
- Deepgram streaming ASR for real-time transcription in Q4.
- Edge TTS for browser-based voice synthesis without an API key.
- Redis event bus for real-time call signal flow.
- FastAPI services running on the host machine.
- React dashboards and web clients for demos and reviewer-facing workflows.
- Heavy compute, including embedding generation and evaluation, runs on Kaggle notebooks while orchestration and vector storage run locally on the developer's machine.

## Setup

1. Install Docker Desktop and confirm `docker --version` works.
2. Install uv: [https://docs.astral.sh/uv/getting-started/installation/](https://docs.astral.sh/uv/getting-started/installation/).
3. Clone the repo.
4. Copy [.env.template](.env.template) to `.env` and fill in credentials.
5. Run `docker compose up -d` to start Qdrant and Redis.
6. Verify Qdrant at [http://localhost:6333/dashboard](http://localhost:6333/dashboard) and Redis via `docker exec ai-assessment-redis redis-cli ping`.

## Per-question documentation

| Question | Directory | Status |
| --- | --- | --- |
| Q1 | `q1-voice-agent/` | Scaffolded — implementation in progress |
| Q2 | `q2-knowledge-base/` | Scaffolded — implementation in progress |
| Q3 | `q3-localized/` | Scaffolded — implementation in progress |
| Q4 | `q4-realtime/` | Scaffolded — implementation in progress |

## Design decisions

See [docs/decisions.md](docs/decisions.md).

## Known limitations

See [docs/limitations.md](docs/limitations.md).

## Notes for reviewers

This repo uses only free-tier APIs and self-hosted open-source components, so it is fully reproducible without paid credentials beyond signup free tiers. Heavy compute runs on Kaggle, so no GPU is required locally. The voice demo is web-based rather than telephony-based, which the assessment explicitly permits.
