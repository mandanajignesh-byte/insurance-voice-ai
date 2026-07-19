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

app = FastAPI(title="Q4 Real-Time Call Insights")
_clients = []

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

@app.get("/")
async def dashboard():
    path = Path(__file__).parent.parent / "dashboard" / "index.html"
    return FileResponse(str(path))

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("Q4_PORT", "7864"))
    logger.info(f"Q4 server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
