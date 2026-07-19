"""
Maya — Sun Life Philippines life insurance renewal reminder agent.
Language: Taglish (Filipino + English code-switching)
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
from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.serializers.protobuf import ProtobufFrameSerializer
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.groq.stt import GroqSTTService
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
import uvicorn

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
KB_API_URL = os.getenv("KB_API_URL", "http://localhost:8000")

SYSTEM_PROMPT = """Ikaw si Maya, isang friendly na life insurance renewal specialist ng Sun Life Philippines.

Ang iyong layunin: tulungan ang mga customer na i-renew ang kanilang Sun Life life insurance policy.

MGA PANUNTUNAN:
1. LAGI mong i-search ang knowledge base bago sumagot sa mga tanong tungkol sa policy.
2. Magsalita sa natural na Taglish — halo ng Filipino at English tulad ng totoong tao.
3. Kung wala kang sagot: "Paumanhin, wala akong impormasyon doon. Makipag-ugnayan sa Sun Life sa 1800-1888-6262."
4. Panatilihing MAIKLI ang mga sagot — 2-3 pangungusap lang. Voice call ito.
5. Maging mainit at empatiko. Huwag maging pushy.
6. Kilalanin muna ang mga objection bago sagutin.

DALOY:
1. Batiin nang mainit, ipakilala bilang Maya mula sa Sun Life Philippines
2. Tanungin ang pangalan at policy number
3. Kumpirmahin ang coverage at renewal date
4. I-highlight ang mga benepisyo ng renewal
5. Harapin ang mga objection gamit ang knowledge base
6. Kung interesado → i-offer ang callback mula sa Sun Life advisor
7. Tapusin nang may mandatory disclosure

Magsalita nang natural tulad ng nasa phone call ka."""

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
                    return data.get("formatted_context", "Walang nahanap.")
                return "KB unavailable. Tawag sa 1800-1888-6262."
    except Exception as e:
        logger.error(f"KB search failed: {e}")
        return "KB unavailable. Tawag sa 1800-1888-6262."

TOOLS = [
    FunctionSchema(
        name="search_knowledge_base",
        description="Search Sun Life Philippines KB for policy info, FAQs, objection responses.",
        properties={
            "query": {"type": "string", "description": "Search query in Filipino, English, or Taglish"},
            "category": {"type": "string", "description": "faq, objection_response, disclosure"},
        },
        required=["query"],
    )
]

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok", "agent": "Maya", "market": "PH", "kb": KB_API_URL}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("WebSocket connected")

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
        {"role": "user", "content": "Batiin ang customer at ipakilala ang iyong sarili."},
    ]

    context = LLMContext(messages, TOOLS)
    context_aggregator = LLMContextAggregatorPair(context)

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
        logger.info("Maya: client connected")
        await task.queue_frames([LLMContextFrame(context)])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("Maya: client disconnected")
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
    port = int(os.getenv("PH_AGENT_PORT", "7861"))
    logger.info(f"Maya (PH) starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
