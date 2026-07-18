"""
Rani — Adira Finance Indonesia cicilan reminder agent.
Language: Bahasa Indonesia (formal + colloquial + finance loanwords)
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

SYSTEM_PROMPT = """Kamu adalah Rani, agen pengingat cicilan yang ramah dari Adira Finance Indonesia.

Tujuanmu: mengingatkan customer tentang jatuh tempo cicilan dan membantu jika ada kesulitan pembayaran.

ATURAN:
1. SELALU cari di knowledge base sebelum menjawab pertanyaan tentang cicilan atau kredit.
2. Gunakan bahasa Indonesia yang natural — campuran formal dan santai sesuai situasi.
3. Gunakan istilah keuangan yang tepat: cicilan, tenor, denda, DP, jatuh tempo, angsuran, pembiayaan.
4. Jika tidak tahu jawaban: "Maaf, saya tidak punya informasi itu. Silakan hubungi Adira di 1500-777."
5. Jawaban SINGKAT — 2-3 kalimat saja. Ini panggilan telepon.
6. Empati dulu sebelum solusi untuk customer yang kesulitan bayar.
7. Tetap gunakan Bahasa Indonesia meskipun customer bicara bahasa lain.

ALUR PERCAKAPAN:
1. Sapa dengan hangat, perkenalkan diri sebagai Rani dari Adira Finance
2. Tanyakan nama dan nomor kontrak kredit
3. Konfirmasi jumlah cicilan dan tanggal jatuh tempo
4. Ingatkan dengan sopan tentang pembayaran yang akan atau sudah jatuh tempo
5. Tangani keberatan dengan empati menggunakan knowledge base
6. Jika perlu restrukturisasi → tawarkan untuk dihubungi oleh tim Adira
7. Tutup dengan informasi penting dan disclaimer

Berbicara dengan natural seperti di telepon sungguhan."""

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
                    return data.get("formatted_context", "Tidak ada informasi yang ditemukan.")
                return "KB tidak tersedia. Hubungi Adira di 1500-777."
    except Exception as e:
        logger.error(f"KB search failed: {e}")
        return "KB tidak tersedia. Hubungi Adira di 1500-777."

TOOLS = [
    FunctionSchema(
        name="search_knowledge_base",
        description="Cari informasi cicilan, denda, tenor, dan cara pembayaran di knowledge base Adira Finance.",
        properties={
            "query": {"type": "string", "description": "Pertanyaan dalam Bahasa Indonesia atau English"},
            "category": {"type": "string", "description": "faq, objection_response, disclosure"},
        },
        required=["query"],
    )
]

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok", "agent": "Rani", "market": "ID", "kb": KB_API_URL}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.info("WebSocket connected — Rani (ID)")

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
        {"role": "user", "content": "Sapa customer dan perkenalkan dirimu sebagai Rani dari Adira Finance."},
    ]

    context = OpenAILLMContext(messages=messages, tools=TOOLS)
    context_aggregator = llm.create_context_aggregator(context)

    vad = VADProcessor(vad_analyzer=SileroVADAnalyzer(
        params=VADParams(confidence=0.8, start_secs=0.3, stop_secs=0.5, min_volume=0.75)
    ))

    rtvi = RTVIProcessor()

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
        logger.info("Rani: client connected")
        await task.queue_frames([context_aggregator.user().get_context_frame()])

    @transport.event_handler("on_client_disconnected")
    async def on_disconnected(transport, client):
        logger.info("Rani: client disconnected")
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
    port = int(os.getenv("ID_AGENT_PORT", "7862"))
    logger.info(f"Rani (ID) starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
