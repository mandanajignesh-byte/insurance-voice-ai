# Known Limitations

Honest notes on what doesn't work perfectly and why.

---

## 1. Background noise / acoustic echo on laptop speakers

**What happens:** When using laptop speakers without headphones, Priya's voice bleeds into the microphone and gets transcribed again, creating a feedback loop. You also hear fan noise in the audio.

**Why:** Browser echo cancellation (`echoCancellation: true`) helps but doesn't fully eliminate acoustic echo when speakers and mic are 10cm apart.

**Fix for demo:** Use headphones. This breaks the acoustic feedback loop completely.

**Production fix:** Use a proper WebRTC stack with server-side acoustic echo cancellation (e.g. Krisp, Deepgram's noise suppression).

---

## 2. BGE-M3 cold start (~15 seconds)

**What happens:** The first KB search of each Codespaces session takes ~15 seconds because BGE-M3 (4.5GB) loads from disk cache.

**Why:** Lazy loading — the model doesn't load until the first request hits the API.

**Fix:** `start.sh` sends a pre-warm request after starting the KB API. The model loads in the background before any call starts. KB timeout in the agent is set to 60 seconds to accommodate this.

**Production fix:** Load the model eagerly on API startup with a `@app.on_event("startup")` handler.

---

## 3. Groq rate limits on free tier

**What happens:** Groq Whisper STT has a token-per-minute and token-per-day limit. During heavy testing (multiple calls back to back), STT can start returning errors.

**Why:** Free tier limits. Groq TTS (Orpheus) hit a 3600 token/day limit during development — that's why we switched to Cartesia.

**Production fix:** Upgrade to Groq paid tier or switch STT to Deepgram (which has better real-time streaming support anyway).

---

## 4. Qdrant storage doesn't persist between Codespaces sessions

**What happens:** Every time a Codespaces session starts fresh, the Qdrant storage is empty. The 273 KB records need to be reloaded.

**Why:** Qdrant runs as a binary with local file storage. Codespaces doesn't persist `/workspaces/` between sessions by default.

**Fix:** `start.sh` runs `python -m retrieval.load_qdrant` every session. Since embeddings are pre-computed (`embeddings.npy`), this takes under 2 seconds.

**Production fix:** Use a persistent Qdrant Cloud instance or a mounted volume.

---

## 5. Q3 recordings not included

**What happens:** The Q3 agents (Maya, Rani, Kavita) are built and running but we don't have recorded test calls for them.

**Why:** Time constraint. The Q3 web client serves on port 8080 but the agents need separate port forwarding setup in Codespaces, and recording sessions for 3 additional agents was deprioritized in favor of getting Q4 working end-to-end.

**What's verifiable:** The agent code is correct, imports work, agents start successfully on ports 7861/7862/7863, the web client shows all 3 tabs correctly.

---

## 6. Q4 receives text not audio

**What happens:** Q4's real-time analysis is based on transcribed text forwarded from Q1's STT output, not raw audio.

**Why:** The AudioTap approach (tapping into Pipecat's audio pipeline) had technical issues with Pipecat 1.5's frame routing. Text forwarding worked cleanly and achieves the same result for signal detection purposes.

**What this means:** Q4 can't detect tone of voice, speaking pace, or audio-level signals like sighing. It only works with what was said.

**Production fix:** Forward raw audio chunks directly to a streaming STT + signal pipeline. Deepgram's real-time API would be the right choice.

---

## 7. Q4 signal quality depends on conversation content

**What happens:** If the call is short or only contains polite exchanges, Q4 generates zero nudges (confidence below 0.65 threshold). The demo call in the screenshots had specific trigger phrases that reliably produce signals.

**Why:** The signal extractor uses a confidence threshold. Low-information transcript windows correctly return "none" rather than hallucinating signals.

**This is a feature, not a bug** — it's better to miss a signal than to fire false alerts. For a real deployment, you'd tune the threshold based on historical call data.

---

## 8. Whisper transcription of non-English speech is imperfect

**What happens:** When testing Q3 agents with actual Taglish or Bahasa speech, Whisper sometimes transliterates instead of transcribing — writing phonetic approximations of Filipino words in English letters.

**Why:** Whisper Large v3 is trained on multilingual data but with uneven coverage. Filipino (Tagalog) and Bahasa Indonesia have less training data than English, Spanish, or Mandarin.

**What was observed:** For Hinglish (Kavita), Whisper performs well because the Hindi portions are often romanized anyway. For Taglish, performance is acceptable for the demo. For pure Bahasa, it works but occasionally misses formal financial terms.

**Production fix:** Fine-tune Whisper on domain-specific multilingual data, or use Google STT which has stronger Southeast Asian language support.

---

## 9. No CI/CD pipeline

There are no automated tests or deployment pipelines. All testing was manual during development.

**Why:** Time constraint for a 48-hour assessment.

**What exists:** The `.devcontainer/` setup ensures anyone can reproduce the environment from scratch with one click.
