"""
Q4 FastAPI server — streams nudges to dashboard via WebSocket.
"""
import os
import asyncio
import json
import time
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

from fastapi.middleware.cors import CORSMiddleware
app = FastAPI(title="Q4 Real-Time Call Insights")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
_clients = []
_transcript_window = []  # list of (timestamp, text) tuples

async def broadcast(data: dict):
    data["delivered_at"] = time.time()
    msg = json.dumps(data)
    dead = []
    for ws in _clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.remove(ws)

@app.get("/health")
def health():
    return {"status": "ok", "clients": len(_clients)}

@app.websocket("/ws/nudges")
async def nudge_stream(websocket: WebSocket):
    await websocket.accept()
    _clients.append(websocket)
    logger.info(f"Dashboard connected. Total: {len(_clients)}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in _clients:
            _clients.remove(websocket)

@app.post("/analyze")
async def analyze_file(file: UploadFile = File(...)):
    from pipeline import RealtimePipeline
    tmp = Path(f"/tmp/q4_{int(time.time())}.wav")
    with open(tmp, "wb") as f:
        f.write(await file.read())
    logger.info(f"Analyzing: {tmp}")

    async def on_nudge(nudge_dict: dict):
        nudge_dict["received_at"] = time.time()
        logger.info(f"NUDGE: {nudge_dict['signal_type']} — {nudge_dict['nudge']}")
        await broadcast(nudge_dict)

    asyncio.create_task(_run(str(tmp), on_nudge))
    return {"status": "started", "file": file.filename}

async def _run(path: str, callback):
    from pipeline import RealtimePipeline
    try:
        p = RealtimePipeline(path, callback)
        await p.run()
        await broadcast({
            "signal_type": "system", "nudge": "Analysis complete",
            "confidence": 1.0, "timestamp": time.time(), "transcript_excerpt": ""
        })
    except Exception as e:
        logger.error(f"Pipeline error: {e}")
        await broadcast({
            "signal_type": "error", "nudge": str(e),
            "confidence": 0, "timestamp": time.time(), "transcript_excerpt": ""
        })

@app.post("/analyze_text")
async def analyze_text(payload: dict):
    """Receive live transcription text from Q1 agent."""
    from pipeline import RealtimePipeline, SignalExtractor
    text = payload.get("text", "").strip()
    if not text:
        return {"status": "empty"}

    # Add to global transcript window
    import time
    _transcript_window.append((time.time(), text))
    # Keep last 20 seconds
    cutoff = time.time() - 20
    while _transcript_window and _transcript_window[0][0] < cutoff:
        _transcript_window.pop(0)

    # Broadcast transcript chunk
    await broadcast({
        "signal_type": "transcript",
        "nudge": "",
        "confidence": 1.0,
        "timestamp": time.time(),
        "transcript_excerpt": text,
    })

    # Extract signal from window
    window_text = " ".join(t for _, t in _transcript_window)
    asyncio.create_task(_extract_signal(window_text))
    return {"status": "ok"}

async def _extract_signal(window_text: str):
    from pipeline import SignalExtractor
    from dataclasses import asdict
    extractor = SignalExtractor()
    nudge = await extractor.extract(window_text)
    if nudge:
        await broadcast(asdict(nudge))

@app.post("/analyze_chunk")
async def analyze_chunk(file: UploadFile = File(...)):
    """Receive a single audio chunk from live call and process it."""
    from pipeline import RealtimePipeline
    chunk_bytes = await file.read()
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp.write(chunk_bytes)
    tmp.close()

    async def on_nudge(nudge_dict: dict):
        nudge_dict["received_at"] = time.time()
        await broadcast(nudge_dict)

    asyncio.create_task(_process_chunk(tmp.name, on_nudge))
    return {"status": "ok"}

async def _process_chunk(path: str, callback):
    from pipeline import RealtimePipeline
    try:
        p = RealtimePipeline(path, callback)
        # Only transcribe, don't simulate real-time delay
        import wave, os
        with wave.open(path, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            sr = wf.getframerate()
        text = await p._transcribe_chunk(frames, sr)
        if text:
            p._transcript_window.append((__import__('time').time(), text))
            await callback({
                "signal_type": "transcript",
                "nudge": "",
                "confidence": 1.0,
                "timestamp": __import__('time').time(),
                "transcript_excerpt": text,
            })
            window = p._get_window_text()
            nudge = await p.extractor.extract(window)
            if nudge:
                await callback(__import__('dataclasses').asdict(nudge))
        os.unlink(path)
    except Exception as e:
        logger.error(f"Chunk processing error: {e}")

@app.get("/")
async def dashboard():
    path = Path(__file__).parent.parent / "dashboard" / "index.html"
    return FileResponse(str(path))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("Q4_PORT", "7864"))
    logger.info(f"Q4 server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
