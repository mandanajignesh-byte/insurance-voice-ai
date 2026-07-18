"""Star Health renewal voice agent powered by Pipecat, Groq, and Qdrant."""

import aiohttp
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMContextFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.groq.stt import GroqSTTService
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketTransport,
    FastAPIWebsocketParams,
)

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
KB_API_URL = os.getenv("KB_API_URL", "http://localhost:8000")


# ── KB retrieval ──────────────────────────────────────────────────────────────


async def search_knowledge_base(query: str, category: str = None) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "query": query,
                "top_k": 4,
                "language": "en",
                "score_threshold": 0.3,
                "format_for_agent": True,
            }
            if category:
                payload["category_filter"] = category
            async with session.post(
                f"{KB_API_URL}/search",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("formatted_context", "No relevant info found.")
                return "KB unavailable. Advise customer to call 1800-425-2255."
    except Exception as e:
        logger.error(f"KB search failed: {e}")
        return "KB unavailable. Advise customer to call 1800-425-2255."


# ── Tools ─────────────────────────────────────────────────────────────────────

TOOLS = [
    FunctionSchema(
        name="search_knowledge_base",
        description="Search the Star Health KB before answering any policy question.",
        properties={"query": {"type": "string"}, "category": {"type": "string"}},
        required=["query"],
    ),
    FunctionSchema(
        name="escalate_to_human",
        description="Escalate to human agent when needed.",
        properties={"reason": {"type": "string"}, "summary": {"type": "string"}},
        required=["reason", "summary"],
    ),
    FunctionSchema(
        name="save_lead",
        description="Save qualified lead when customer shows purchase interest.",
        properties={
            "name": {"type": "string"},
            "phone": {"type": "string"},
            "interest_level": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "notes": {"type": "string"},
        },
        required=["name", "interest_level"],
    ),
]

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Priya, a friendly health insurance renewal specialist at Star Health India.

Your goal: help customers understand and renew their Family Health Optima Insurance Plan.

RULES:
1. ALWAYS call search_knowledge_base before answering policy questions. Never invent facts.
2. If KB has no answer say: "I don't have that specific information. Call us at 1800-425-2255."
3. Keep responses SHORT — max 2-3 sentences. This is a voice call.
4. Be warm and empathetic. Never pushy.
5. Acknowledge objections first, then search objection_response.
6. Read disclosure records VERBATIM.

FLOW:
1. Greet warmly, introduce as Priya from Star Health
2. Ask name and policy number
3. Confirm Family Health Optima coverage
4. Highlight key renewal benefits
5. Handle objections using KB
6. If interested → save_lead → offer callback
7. End with mandatory disclosure

Speak naturally as if on a phone call."""


# ── Agent runner ──────────────────────────────────────────────────────────────


async def run_agent(websocket: WebSocket):
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_in_sample_rate=16000,
            audio_out_enabled=True,
            audio_out_sample_rate=48000,
            add_wav_header=True,
            serializer=ProtobufFrameSerializer(),
            audio_in_passthrough=True,
        ),
    )

    llm = GroqLLMService(
        api_key=GROQ_API_KEY,
        model="qwen/qwen3.6-27b",
    )

    stt = GroqSTTService(
        api_key=GROQ_API_KEY,
        model="whisper-large-v3",
    )

    tts = CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id="248be419-c632-4f23-adf1-5324ed7dbf1d",
        sample_rate=48000,
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": "Please greet the customer and introduce yourself.",
        },
    ]

    context = LLMContext(messages, TOOLS)
    context_aggregator = LLMContextAggregatorPair(context)

    async def handle_tool_call(params: FunctionCallParams):
        function_name = params.function_name
        arguments = params.arguments
        if function_name == "search_knowledge_base":
            result = await search_knowledge_base(
                arguments.get("query", ""),
                arguments.get("category"),
            )
            logger.info(f"KB search: '{arguments.get('query')}' → {len(result)} chars")
            await params.result_callback(result)

        elif function_name == "escalate_to_human":
            logger.info(f"ESCALATION: {arguments.get('reason')}")
            log_dir = Path(__file__).parent.parent / "recordings"
            log_dir.mkdir(exist_ok=True)
            with open(log_dir / "escalations.jsonl", "a") as f:
                json.dump(arguments, f)
                f.write("\n")
            await params.result_callback("Escalation logged. Transfer to 1800-425-2255.")

        elif function_name == "save_lead":
            logger.info(f"LEAD: {arguments}")
            log_dir = Path(__file__).parent.parent / "recordings"
            log_dir.mkdir(exist_ok=True)
            with open(log_dir / "leads.jsonl", "a") as f:
                json.dump(arguments, f)
                f.write("\n")
            await params.result_callback(f"Lead saved for {arguments.get('name')}.")

    llm.register_function(None, handle_tool_call)
    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer())

    pipeline = Pipeline(
        [
            transport.input(),
            vad,
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=48000,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info("Client connected — sending greeting")
        await task.queue_frames([LLMContextFrame(context)])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("Client disconnected")
        await task.cancel()

    await PipelineRunner().run(task)


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Star Health Voice Agent")

WEB_CLIENT_DIR = Path(__file__).parent.parent / "web-client" / "dist"


@app.get("/health")
async def health():
    return {"status": "ok", "kb": KB_API_URL}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connected")
    try:
        await run_agent(websocket)
    except Exception as e:
        logger.error(f"Agent error: {e}")


if WEB_CLIENT_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(WEB_CLIENT_DIR), html=True),
        name="static",
    )


if __name__ == "__main__":
    import uvicorn

    logger.info(f"KB API: {KB_API_URL}")
    logger.info("Web client dev: http://localhost:5173")
    uvicorn.run(app, host="0.0.0.0", port=7860)
