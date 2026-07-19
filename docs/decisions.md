# Key Design Decisions

Short answers to "why did you do it this way?" for each major choice.

---

## Domain — Star Health India (Q1), Sun Life PH (Q3-PH), Adira Finance (Q3-ID)

**Why Star Health for Q1?**
Star Health is India's largest standalone health insurer. Their Family Health Optima plan is well-documented publicly — real FAQs, real policy clauses, real objection scenarios. This meant the KB could use actual content rather than invented data.

**Why Sun Life for Q3-PH?**
Sun Life is the most recognized life insurance brand in the Philippines. Their renewal flow is a natural fit for an outbound voice agent use case.

**Why Adira Finance for Q3-ID?**
Adira is Indonesia's largest multifinance company (owned by Bank Danamon). The cicilan/installment reminder use case is one of the highest-volume voice agent deployments in Indonesian fintech.

---

## VAD Settings — confidence 0.8, min_volume 0.75

Default Silero VAD settings were too sensitive — they picked up fan noise, Priya's speaker output bleeding into the mic, and ambient room noise. Raising the confidence threshold and minimum volume significantly reduced false positives.

This is why the transcript shows mostly meaningful speech rather than background noise being transcribed.

---

## Echo cancellation — browser MediaStream constraints

Added `echoCancellation: true, noiseSuppression: true, autoGainControl: true` to the browser mic constraints. This is browser-native echo cancellation — it reduces the speaker bleed into the mic when using laptop speakers. Still not perfect without headphones, but significantly better than without.

---

## KB timeout — 60 seconds

BGE-M3 takes ~15 seconds to load from cache on first search. The original 30-second timeout was causing KB failures during the first call of each session. Extended to 60 seconds so the model has time to load before the request times out.

Combined with the pre-warm step in `start.sh`, this effectively eliminates cold-start KB failures.

---

## Lead saving — local JSONL file

Leads are saved to `q1-voice-agent/recordings/leads.jsonl`. In production this would go to a CRM. For the assessment, a local file is sufficient to demonstrate the concept and provides a readable audit trail.

Format:
```json
{"name": "Jignesh", "phone": "6359724924", "interest": "Family Health Optima", "timestamp": "2026-07-19T..."}
```

---

## Q4 signal cooldown — 30 seconds per signal type

Without a cooldown, the same signal fires repeatedly on every 5-second analysis window. A 30-second cooldown per signal type means each type fires at most twice per minute. This keeps the dashboard readable and prevents alert fatigue.

---

## Q3 web client — single HTML file served with python -m http.server

The Q3 web client is a standalone HTML file with vanilla JS — no build step, no npm, no Vite. This was deliberate: the Q3 agents are secondary to Q1, and a simple static HTML file is faster to iterate on and easier to serve in Codespaces without port conflicts.

The downside is that it imports Pipecat client from a CDN which is slightly slower on first load.

---

## No phone number — browser WebSocket only

The assessment doesn't require a phone number. WebSocket transport in the browser is equivalent for demonstrating the voice agent capability. It also means the demo works from any machine with a browser without any telephony setup.
