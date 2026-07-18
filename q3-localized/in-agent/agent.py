"""
Kavita — Star Health India renewal reminder agent (Hinglish bonus).
Language: Hinglish (Hindi + English natural code-switching)
"""
import os
import aiohttp
from dotenv import load_dotenv
from loguru import logger
from fastapi import FastAPI, WebSocket
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.openai_llm_context import OpenAILLMContext
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frameworks.rtvi import RTVIProcessor
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.groq.stt import GroqSTTService
from pipecat.services.llm_service import FunctionSchema
from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
import uvicorn

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
KB_API_URL = os.getenv("KB_API_URL", "http://localhost:8000")

SYSTEM_PROMPT = """Aap Kavita hain, Star Health India ki ek friendly health insurance renewal specialist.

Aapka goal: customers ko unki Family Health Optima policy renew karne mein help karna.

RULES:
1. HAMESHA knowledge base search karo policy questions ka jawab dene se pehle.
2. Natural Hinglish mein baat karo — jaise real Indian customer care agent bolte hain.
   Example: "Aapki policy ka renewal date kya hai?" ya "Sir, aapko koi tension nahi leni."
3. Agar answer nahi pata: "Mujhe is baare mein puri jaankari nahi hai. Aap hamare helpline 1800-425-2255 pe call kar sakte hain."
4. Jawab CHOTA rakho — 2-3 sentences. Yeh phone call hai.
5. Warm aur empathetic raho. Pushy mat bano.
6. Pehle objection acknowledge karo, phir KB se jawab do.

CONVERSATION FLOW:
1. Warmly greet karo, Kavita ke roop mein Star Health se introduce karo
2. Naam aur policy number pucho
3. Family Health Optima coverage confirm karo
4. Renewal ke benefits highlight karo
5. Objections handle karo KB se
6. Interested ho toh → callback offer karo
7. Mandatory disclosure ke saath end karo

Natural baat karo jaise real phone call pe hote hain."""

async def search_knowledge_base(query: str, category: str = None) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "query": query,
                "top_k": 3,
                "score_threshold": 0.2,
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
                    return data.get("formatted_context", "Koi relevant information nahi mili.")
                return "KB unavailable. 1800-425-2255 pe call karein."
    except Exception as e:
        logger.error(f"KB search failed: {e}")
        return "KB unavailable. 1800-425-2255 pe call karein."

TOOLS = [
    FunctionSchema(
        name="search_knowledge_base",
        description="Search Star Health India KB for policy info, FAQs, objection responses in Hindi or English.",
        properties={
            "query": {"type": "string", "description": "Search query in Hindi, English, or Hinglish"},
            "category": {"type": "string", "description": "faq, objection_response, disclosure, policy_terms"},
        },
        required=["query"],
    )
]

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok", "agent": "Kavita", "market": "IN", "language": "Hinglish", "kb": KB_API_URL}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("WebSocket connected — Kavita (IN)")

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            add_wav_header=False,
            vad_enabled=False,
            serializer=ProtobufFrameSerializer(),
            audio_in_sample_rate=16000,
            audio_out_sample_rate=48000,
        ),
    )

    llm = GroqLLMService(
        api_key=GROQ_API_KEY,
        settings=GroqLLMService.Settings(model="qwen/qwen3.6-27b"),
        tools=TOOLS,
    )

    stt = GroqSTTService(
        api_key=GROQ_API_KEY,
        settings=GroqSTTService.Settings(model="whisper-large-v3"),
    )

    tts = CartesiaTTSService(
        api_key=CARTESIA_API_KEY,
        settings=CartesiaTTSService.Settings(
            voice="a7a59115-2425-4192-844c-1e98ec7d6877",
            sample_rate=48000,
        ),
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Customer ko greet karo aur apna introduction do."},
    ]

    context = OpenAILLMContext(messages=messages, tools=TOOLS)
    context_aggregator = llm.create_context_aggregator(context)

    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer(
        params=VADParams(confidence=0.8, start_secs=0.3, stop_secs=0.5, min_volume=0.75)
    ))

    pipeline = Pipeline([
        transport.input(),
        vad,
        stt,
        context_aggregator.user(),
        llm,
        tts,
        transport.output(),
        context_aggregator.assistant(),
    ])

    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))

    @transport.event_handler("on_client_connected")
    async def on_connected(transport, client):
        logger.info("Kavita: client connected")
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("Kavita: client disconnected")
        await task.cancel()

    async def handle_tool_call(params: dict):
        fn = params.function_name
        args = params.arguments
        if fn == "search_knowledge_base":
            result = await search_knowledge_base(
                args.get("query", ""),
                args.get("category"),
            )
            logger.info(f"KB: '{args.get('query')}' → {len(result)} chars")
            await params.result_callback(result)

    llm.register_function(None, handle_tool_call)

    runner = PipelineRunner()
    await runner.run(task)

if __name__ == "__main__":
    port = int(os.getenv("IN_AGENT_PORT", "7863"))
    logger.info(f"Kavita (IN/Hinglish) starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
