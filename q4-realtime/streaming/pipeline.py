"""
Q4 Real-Time Call Insights Pipeline.
Replays a WAV recording at 1x speed, transcribes in chunks,
extracts signals, and pushes nudges via WebSocket.
"""
import os
import json
import time
import asyncio
import wave
import struct
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict
from loguru import logger
import aiohttp
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CHUNK_SECS = 3          # audio chunk size sent to STT
WINDOW_SECS = 20        # rolling transcript window for signal extraction
SIGNAL_INTERVAL = 5     # run signal extraction every N seconds
CONFIDENCE_THRESHOLD = 0.65  # minimum confidence to emit nudge
COOLDOWN_SECS = 30      # don't repeat same signal type within N seconds

@dataclass
class Nudge:
    timestamp: float
    signal_type: str
    nudge: str
    confidence: float
    transcript_excerpt: str

SIGNAL_PROMPT = """/no_think
You are a real-time call quality analyst. Analyze this transcript excerpt from an insurance/finance call and identify ONE most important signal if present.

TRANSCRIPT (last 20 seconds):
{transcript}

/no_think
Respond ONLY with valid JSON, no markdown:
{{
  "signal_type": "missed_cross_sell" | "compliance_gap" | "rising_frustration" | "buying_signal" | "payment_difficulty" | "none",
  "nudge": "Short actionable recommendation for the agent (max 15 words). Empty string if none.",
  "confidence": 0.0-1.0,
  "reasoning": "One sentence why"
}}

Rules:
- Only flag HIGH confidence signals (>0.65)
- Return signal_type "none" if no clear signal
- Nudge must be actionable and specific
- Do not repeat obvious or low-value alerts"""

class SignalExtractor:
    def __init__(self):
        self.client = AsyncGroq(api_key=GROQ_API_KEY)
        self._last_signal_time: dict[str, float] = {}

    def _is_on_cooldown(self, signal_type: str) -> bool:
        last = self._last_signal_time.get(signal_type, 0)
        return (time.time() - last) < COOLDOWN_SECS

    async def extract(self, transcript_window: str) -> Optional[Nudge]:
        if not transcript_window.strip():
            return None
        try:
            t0 = time.time()
            resp = await self.client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": SIGNAL_PROMPT.format(transcript=transcript_window)}],
                max_tokens=200,
                temperature=0.1,
            )
            latency_ms = (time.time() - t0) * 1000
            raw = resp.choices[0].message.content.strip()
            # Extract JSON even if wrapped in markdown or thinking tags
            import re
            json_match = re.search(r'\{[^{}]+\}', raw, re.DOTALL)
            if json_match:
                raw = json_match.group(0)
            data = json.loads(raw)
            signal_type = data.get("signal_type", "none")
            confidence = float(data.get("confidence", 0))
            nudge_text = data.get("nudge", "").strip()

            logger.debug(f"Signal: {signal_type} ({confidence:.2f}) in {latency_ms:.0f}ms")

            if signal_type == "none" or confidence < CONFIDENCE_THRESHOLD or not nudge_text:
                return None
            if self._is_on_cooldown(signal_type):
                logger.debug(f"Signal {signal_type} on cooldown")
                return None

            self._last_signal_time[signal_type] = time.time()
            excerpt = transcript_window[-200:] if len(transcript_window) > 200 else transcript_window
            return Nudge(
                timestamp=time.time(),
                signal_type=signal_type,
                nudge=nudge_text,
                confidence=confidence,
                transcript_excerpt=excerpt,
            )
        except Exception as e:
            logger.error(f"Signal extraction failed: {e}")
            return None


class RealtimePipeline:
    def __init__(self, wav_path: str, nudge_callback):
        self.wav_path = wav_path
        self.nudge_callback = nudge_callback
        self.client = AsyncGroq(api_key=GROQ_API_KEY)
        self.extractor = SignalExtractor()
        self._transcript_window: list[tuple[float, str]] = []
        self._latencies: list[dict] = []

    def _get_window_text(self) -> str:
        now = time.time()
        self._transcript_window = [
            (t, txt) for t, txt in self._transcript_window
            if now - t <= WINDOW_SECS
        ]
        return " ".join(txt for _, txt in self._transcript_window)

    async def _transcribe_chunk(self, audio_bytes: bytes, sample_rate: int) -> Optional[str]:
        t0 = time.time()
        try:
            import io
            buf = io.BytesIO()
            with wave.open(buf, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_bytes)
            buf.seek(0)
            buf.name = "chunk.wav"
            resp = await self.client.audio.transcriptions.create(
                file=("chunk.wav", buf.read(), "audio/wav"),
                model="whisper-large-v3",
                language="en",
                response_format="text",
            )
            latency_ms = (time.time() - t0) * 1000
            text = resp.strip() if isinstance(resp, str) else ""
            if text:
                logger.info(f"STT ({latency_ms:.0f}ms): {text}")
                self._latencies.append({"stage": "stt", "ms": latency_ms})
            return text or None
        except Exception as e:
            logger.error(f"STT failed: {e}")
            return None

    async def run(self):
        logger.info(f"Starting pipeline on: {self.wav_path}")
        with wave.open(self.wav_path, 'rb') as wf:
            sample_rate = wf.getframerate()
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            chunk_frames = sample_rate * CHUNK_SECS

        last_signal_time = 0

        with wave.open(self.wav_path, 'rb') as wf:
            chunk_idx = 0
            while True:
                frames = wf.readframes(chunk_frames)
                if not frames:
                    break

                chunk_start = time.time()

                # Convert to mono if stereo
                if channels == 2:
                    samples = struct.unpack(f"<{len(frames)//2}h", frames)
                    mono = [(samples[i] + samples[i+1]) // 2 for i in range(0, len(samples), 2)]
                    frames = struct.pack(f"<{len(mono)}h", *mono)

                # Transcribe chunk
                text = await self._transcribe_chunk(frames, sample_rate)
                if text:
                    self._transcript_window.append((time.time(), text))
                    await self.nudge_callback({
                        "signal_type": "transcript",
                        "nudge": "",
                        "confidence": 1.0,
                        "timestamp": time.time(),
                        "transcript_excerpt": text,
                    })

                # Extract signals every SIGNAL_INTERVAL seconds
                now = time.time()
                if now - last_signal_time >= SIGNAL_INTERVAL:
                    last_signal_time = now
                    window = self._get_window_text()
                    if window:
                        t0 = time.time()
                        nudge = await self.extractor.extract(window)
                        if nudge:
                            llm_ms = (time.time() - t0) * 1000
                            self._latencies.append({"stage": "llm", "ms": llm_ms})
                            await self.nudge_callback(asdict(nudge))

                # Real-time simulation — wait the remaining chunk duration
                elapsed = time.time() - chunk_start
                sleep_time = max(0, CHUNK_SECS - elapsed)
                await asyncio.sleep(sleep_time)
                chunk_idx += 1

        logger.info("Pipeline complete")
        self._report_latency()

    def _report_latency(self):
        stt = [x["ms"] for x in self._latencies if x["stage"] == "stt"]
        llm = [x["ms"] for x in self._latencies if x["stage"] == "llm"]
        if stt:
            stt_sorted = sorted(stt)
            p50 = stt_sorted[len(stt_sorted)//2]
            p95 = stt_sorted[int(len(stt_sorted)*0.95)]
            logger.info(f"STT latency — P50: {p50:.0f}ms P95: {p95:.0f}ms")
        if llm:
            llm_sorted = sorted(llm)
            p50 = llm_sorted[len(llm_sorted)//2]
            p95 = llm_sorted[int(len(llm_sorted)*0.95)]
            logger.info(f"LLM latency — P50: {p50:.0f}ms P95: {p95:.0f}ms")
