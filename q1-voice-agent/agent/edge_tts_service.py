import io
import asyncio
import edge_tts
import numpy as np
from pydub import AudioSegment
from pipecat.frames.frames import AudioRawFrame, TTSStartedFrame, TTSStoppedFrame
from pipecat.services.tts_service import TTSService
from loguru import logger


class EdgeTTSService(TTSService):
    def __init__(self, voice: str = "en-IN-NeerjaNeural", sample_rate: int = 48000, **kwargs):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._voice = voice
        self._sample_rate = sample_rate

    async def run_tts(self, text: str):
        logger.debug(f"EdgeTTSService: Generating TTS [{text}]")
        try:
            await self.push_frame(TTSStartedFrame())

            communicate = edge_tts.Communicate(text, voice=self._voice)
            mp3_buffer = io.BytesIO()

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_buffer.write(chunk["data"])

            mp3_buffer.seek(0)
            audio = AudioSegment.from_mp3(mp3_buffer)
            audio = audio.set_frame_rate(self._sample_rate).set_channels(1).set_sample_width(2)
            pcm = np.frombuffer(audio.raw_data, dtype=np.int16)

            chunk_size = self._sample_rate // 10  # 100ms chunks
            for i in range(0, len(pcm), chunk_size):
                chunk = pcm[i:i + chunk_size].tobytes()
                await self.push_frame(AudioRawFrame(audio=chunk, sample_rate=self._sample_rate, num_channels=1))

            await self.push_frame(TTSStoppedFrame())

        except Exception as e:
            logger.error(f"EdgeTTSService error: {e}")
