# Architecture Decisions

This document explains the key technical choices made during this assessment and the honest reasons behind each one.

---

## 1. Why Pipecat instead of Vapi or Retell

The original plan was to use Vapi — it has a hosted phone number, a dashboard, and fast setup. We switched to **Pipecat** for three reasons:

- Vapi charges per minute. Pipecat is fully self-hosted and free.
- Pipecat 1.5 gives direct access to every stage of the audio pipeline — VAD, STT, LLM, TTS — which is what the assessment is actually testing.
- Pipecat runs over WebSocket in the browser, so no phone number is needed and the demo works from any machine.

The tradeoff: Pipecat requires more code. You wire the pipeline yourself instead of clicking buttons in a dashboard. This was intentional — it shows deeper understanding of how voice AI actually works.

---

## 2. Why Groq for STT and LLM

**STT:** Groq runs Whisper Large v3 at ~150-200ms per 3-second chunk — fast enough for real-time conversation. The free tier is generous enough for development and demos.

**LLM:** We went through three models:
- `llama-3.3-70b-versatile` — deprecated by Groq in June 2026
- `llama3-groq-70b-8192-tool-use-preview` — also decommissioned
- `qwen/qwen3.6-27b` — currently active, good tool-calling, but has a thinking mode that returns empty JSON if not handled correctly
- Signal extraction in Q4 uses `llama-3.1-8b-instant` — faster, simpler JSON output, no thinking mode

**Honest limitation:** Groq free tier rate limits are tight. Groq TTS (Orpheus) hit a 3600 token/day limit during testing — which is why we switched to Cartesia.

---

## 3. Why Cartesia for TTS instead of Orpheus or Edge TTS

Three TTS options were tried:

| Option | Result |
|---|---|
| Groq Orpheus (diana, autumn voices) | Background hiss in audio output |
| Groq Orpheus (hannah, luna, tara) | Either decommissioned or invalid voice IDs |
| Edge TTS (Microsoft) | Works but needs ffmpeg for MP3 decode — not available in Codespaces |
| Cartesia | Clean audio, no rate limits on free tier, works instantly |

Cartesia was the right call. Voice used: `a7a59115-2425-4192-844c-1e98ec7d6877` (Amber - Warm Support Agent).

---

## 4. Why BGE-M3 for embeddings

BGE-M3 is multilingual (100+ languages), 1024-dimensional, and runs fully locally — no API cost. For an insurance KB that will eventually serve Filipino, Indonesian, and Hindi content, a multilingual model is the right choice over an English-only model like `text-embedding-ada-002`.

**Tradeoff:** BGE-M3 is 4.5GB. First load takes ~15 seconds from cache. We pre-warm it on startup to avoid this during calls.

The embeddings for 273 records were pre-computed on Kaggle (free GPU) and stored as `embeddings.npy`. Qdrant loads them in under 1 second.

---

## 5. Why Qdrant over pgvector or FAISS

- **FAISS** — fast but in-memory only, no persistence, no metadata filtering
- **pgvector** — good if you already have PostgreSQL, adds complexity for a standalone KB
- **Qdrant** — purpose-built for vector search, has a REST API, supports payload filtering by category/product, and runs as a single binary with no dependencies

For this assessment, Qdrant binary was downloaded and run directly (no Docker) to avoid the Docker-in-Docker issues in Codespaces.

---

## 6. Why GitHub Codespaces instead of running locally

The project was originally developed on a Windows laptop. It caused:
- High CPU/fan from VS Code indexing `.venv` and `node_modules`
- Folder rename issues due to Windows file locking
- No HTTPS for browser mic access (`getUserMedia` requires HTTPS or localhost)

Codespaces solved all three. The tradeoff is that the BGE-M3 model and Qdrant storage don't persist between sessions, so we wrote a `start.sh` startup script that restores everything in one command.

---

## 7. Why the KB has 273 records instead of thousands

Quality over quantity. Each record was written to cover a specific scenario:
- FAQs about the product
- Common objections with empathetic responses
- Policy clause excerpts (verbatim where required)
- Disclosures (marked `verbatim_required: true`)

273 well-structured records with real content outperform 10,000 scraped paragraphs with noise. The retrieval scores on the test queries confirm this — top results consistently score 0.54–0.65 which indicates genuine semantic match, not keyword overlap.

---

## 8. Q4 real-time approach — text forwarding vs audio streaming

Two approaches were considered for Q4:

**Option A — Audio streaming:** Tap into Pipecat's audio pipeline, send raw PCM chunks to Q4 for Whisper transcription. Tried this — the AudioTap class approach failed due to Pipecat's internal frame routing.

**Option B — Text forwarding:** Forward the already-transcribed text from Pipecat's STT callbacks to Q4 via HTTP POST. This worked cleanly.

We went with Option B. The latency is ~1ms for text delivery + ~500ms for LLM signal extraction = ~503ms total from speech to nudge on screen. This is well within the "during the call, not after" requirement.

**Tradeoff:** Q4 receives transcribed text, not raw audio. This means Q4 can't detect tone of voice or disfluencies (um, uh). A production system would use audio. For this assessment, text-based signal extraction is sufficient to demonstrate the concept.

---

## 9. Q3 language strategy

The assessment says "do not do literal translation." We followed this:

- **Maya (PH):** System prompt written in Taglish with natural Filipino-English mixing. KB entries authored in Tagalog with English loanwords, not Google-translated from English.
- **Rani (ID):** System prompt in formal Bahasa Indonesia with natural finance loanwords (cicilan, tenor, denda, jatuh tempo). KB entries use real Adira Finance terminology.
- **Kavita (IN, bonus):** Hinglish system prompt. Uses romanized Hindi naturally mixed with English as real Indian call center agents speak.

Whisper Large v3 handles code-switching without any fine-tuning. This was verified during testing — it correctly transcribed "Hi Priya, it's nice to meet you" even when ambient noise was present.
