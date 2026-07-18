"""
Compatibility entrypoint for the web voice demo.

Run:
    python q1-voice-agent/agent/web_handler.py
"""

from agent import app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=7860)
