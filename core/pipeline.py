"""
Main Pipecat pipeline for the English Coach Agent.
Connects STT → LLM → TTS in a real-time audio pipeline.

Uses Pipecat's transport-based architecture:
  Microphone → VAD → STT → LLM → TTS → Speaker

The pipeline processes audio frames asynchronously with barge-in support.
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

import numpy as np

from config.settings import (
    STT_SAMPLE_RATE,
    STT_CHUNK_SIZE_MS,
    STT_SILENCE_THRESHOLD_MS,
)
from config.logging_config import setup_logging
from stt.vad_handler import SileroVADHandler, VADConfig, VADState
from stt.whisper_stt import WhisperSTTService, WhisperConfig, TranscriptionResult
from llm.deepseek_client import DeepSeekClient, LLMResponse
from llm.response_processor import ResponseProcessor, ProcessedResponse
from tts.edge_tts_handler import EdgeTTSService, TTSConfig
from tts.audio_player import AudioPlayer, AudioConfig

logger = setup_logging()


class PipelineState(Enum):
    IDLE = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    THINKING = auto()
    SPEAKING = auto()
    PAUSED = auto()
    ERROR = auto()


@dataclass
class PipelineConfig:
    sample_rate: int = STT_SAMPLE_RATE
    chunk_size_ms: int = STT_CHUNK_SIZE_MS
    silence_threshold_ms: int = STT_SILENCE_THRESHOLD_MS
    max_conversation_duration_minutes: int = 60


@dataclass
class TurnResult:
    user_text: str
    agent_text: str
    corrections: list = field(default_factory=list)
    new_vocabulary: list = field(default_factory=list)
    latency_stt: float = 0.0
    latency_llm: float = 0.0
    latency_tts: float = 0.0
    total_latency: float = 0.0


class Pipeline:
    """
    Main conversation pipeline for the English Coach Agent.

    Flow:
    1. VAD detects when user starts speaking
    2. Audio is buffered until silence is detected
    3. STT transcribes the utterance
    4. LLM generates a response
    5. TTS synthesizes the response
    6. Audio is played through speakers

    Supports barge-in: if user speaks while agent is talking,
    the TTS output is interrupted and the pipeline listens again.
    """

    def __init__(
        self,
        stt_service: WhisperSTTService,
        llm_client: DeepSeekClient,
        tts_service: EdgeTTSService,
        audio_player: AudioPlayer,
        vad_handler: SileroVADHandler | None = None,
        response_processor: ResponseProcessor | None = None,
        config: PipelineConfig | None = None,
    ):
        self.stt = stt_service
        self.llm = llm_client
        self.tts = tts_service
        self.player = audio_player
        self.vad = vad_handler or SileroVADHandler()
        self.processor = response_processor or ResponseProcessor()
        self.config = config or PipelineConfig()

        self._state = PipelineState.IDLE
        self._audio_buffer: list[np.ndarray] = []
        self._is_collecting = False
        self._conversation_active = False
        self._pause_event = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pause_event.set()  # Not paused initially

        # Callbacks
        self._on_state_change: list[callable] = []
        self._on_transcription: list[callable] = []
        self._on_response: list[callable] = []
        self._on_correction: list[callable] = []
        self._on_turn_complete: list[callable] = []
        self._on_error: list[callable] = []

    # === State management ===

    @property
    def state(self) -> PipelineState:
        return self._state

    def set_state(self, new_state: PipelineState):
        old_state = self._state
        self._state = new_state
        logger.debug(f"Pipeline state: {old_state.name} → {new_state.name}")
        for cb in self._on_state_change:
            try:
                result = cb(new_state, old_state)
                if result is not None and asyncio.iscoroutine(result):
                    asyncio.ensure_future(result)
            except Exception:
                pass

    # === Event callbacks ===

    def on_state_change(self, callback):
        self._on_state_change.append(callback)

    def on_transcription(self, callback):
        self._on_transcription.append(callback)

    def on_response(self, callback):
        self._on_response.append(callback)

    def on_correction(self, callback):
        self._on_correction.append(callback)

    def on_turn_complete(self, callback):
        self._on_turn_complete.append(callback)

    def on_error(self, callback):
        self._on_error.append(callback)

    # === Core pipeline logic ===

    async def start(self):
        """Initialize and start the pipeline."""
        logger.info("Starting English Coach Agent pipeline...")

        # Initialize VAD
        await self.vad.initialize()

        # Wire up VAD callbacks
        self.vad.on_speech_start(self._handle_speech_start)
        self.vad.on_speech_end(self._handle_speech_end)

        self._conversation_active = True
        self.set_state(PipelineState.LISTENING)

        logger.info("Pipeline started — listening for speech...")

    async def stop(self):
        """Gracefully stop the pipeline."""
        logger.info("Stopping pipeline...")
        self._conversation_active = False
        self.player.interrupt()
        self.tts.reset()
        self.vad.reset()
        self.set_state(PipelineState.IDLE)
        logger.info("Pipeline stopped")

    def pause(self):
        """Pause voice activity detection (agent stops listening)."""
        self._pause_event.clear()
        self.set_state(PipelineState.PAUSED)
        logger.info("Pipeline paused")

    def resume(self):
        """Resume voice activity detection."""
        self._pause_event.set()
        self.set_state(PipelineState.LISTENING)
        logger.info("Pipeline resumed")

    async def process_audio_chunk(self, audio_chunk: np.ndarray):
        """
        Feed an audio chunk from the microphone into the pipeline.
        This is the main entry point for audio data.

        Args:
            audio_chunk: float32 numpy array of PCM audio at 16kHz
        """
        if not self._conversation_active:
            return

        await self._pause_event.wait()  # Honor pause state

        # Run VAD on the chunk
        await self.vad.process_audio(audio_chunk)

        # If we're collecting speech, buffer the audio
        if self._is_collecting:
            self._audio_buffer.append(audio_chunk.copy())

    async def _handle_speech_start(self):
        """Called when VAD detects speech starting."""
        logger.debug("Speech detected — starting audio capture")
        self._is_collecting = True
        self._audio_buffer.clear()

        # Interrupt TTS if agent is currently speaking (barge-in)
        if self._state == PipelineState.SPEAKING:
            logger.debug("Barge-in: interrupting agent speech")
            self.player.interrupt()
            self.tts.interrupt()

        self.set_state(PipelineState.LISTENING)

    async def _handle_speech_end(self):
        """Called when VAD detects speech ending (silence)."""
        if not self._is_collecting or not self._audio_buffer:
            return

        self._is_collecting = False
        logger.debug(f"Speech ended — captured {len(self._audio_buffer)} chunks")

        # Process the utterance through the pipeline
        await self._process_utterance()

    async def _process_utterance(self):
        """Process a complete utterance through STT → LLM → TTS."""
        if not self._audio_buffer:
            return

        turn_start = time.monotonic()

        try:
            # Phase 1: STT - Transcribe speech to text
            self.set_state(PipelineState.TRANSCRIBING)

            audio_data = np.concatenate(self._audio_buffer)
            audio_data = audio_data.astype(np.float32)

            stt_start = time.monotonic()
            transcription: TranscriptionResult = await self.stt.transcribe(audio_data)
            stt_latency = time.monotonic() - stt_start

            user_text = transcription.text.strip()

            if not user_text:
                logger.debug("Empty transcription — skipping")
                self.set_state(PipelineState.LISTENING)
                return

            logger.info(f"User said: '{user_text}'")

            for cb in self._on_transcription:
                await cb(user_text)

            # Phase 2: LLM - Generate response
            self.set_state(PipelineState.THINKING)

            llm_start = time.monotonic()
            response: LLMResponse = await self.llm.chat(user_text)
            llm_latency = time.monotonic() - llm_start

            logger.info(f"Agent says: '{response.content[:100]}...'")

            # Process the response
            processed: ProcessedResponse = self.processor.process(response.content)

            for cb in self._on_response:
                await cb(processed)

            # Notify corrections
            for correction in processed.corrections:
                for cb in self._on_correction:
                    await cb(correction)

            # Phase 3: TTS - Synthesize and play response
            if processed.conversational_text:
                self.set_state(PipelineState.SPEAKING)

                tts_start = time.monotonic()

                # Interrupt TTS if user starts speaking during synthesis
                try:
                    audio_bytes = await self.tts.synthesize(
                        processed.conversational_text
                    )

                    if not self.tts.is_interrupted:
                        await self.player.play_bytes(audio_bytes)

                    tts_latency = time.monotonic() - tts_start
                except Exception as e:
                    logger.error(f"TTS/playback error: {e}")
                    tts_latency = time.monotonic() - tts_start

                total_latency = time.monotonic() - turn_start

                turn_result = TurnResult(
                    user_text=user_text,
                    agent_text=processed.conversational_text,
                    corrections=processed.corrections,
                    new_vocabulary=processed.new_vocabulary,
                    latency_stt=stt_latency,
                    latency_llm=llm_latency,
                    latency_tts=tts_latency,
                    total_latency=total_latency,
                )

                logger.info(
                    f"Turn complete ({total_latency:.2f}s) — "
                    f"STT: {stt_latency:.2f}s, LLM: {llm_latency:.2f}s, "
                    f"TTS: {tts_latency:.2f}s"
                )

                for cb in self._on_turn_complete:
                    await cb(turn_result)

        except Exception as e:
            logger.error(f"Pipeline error processing utterance: {e}")
            self.set_state(PipelineState.ERROR)
            for cb in self._on_error:
                await cb(str(e))
        finally:
            if self._state != PipelineState.ERROR:
                self.set_state(PipelineState.LISTENING)

    async def send_text(self, text: str) -> TurnResult:
        """
        Process text input directly (bypasses STT).
        Useful for testing or typed input.
        """
        start = time.monotonic()

        self.set_state(PipelineState.THINKING)

        response: LLMResponse = await self.llm.chat(text)
        processed: ProcessedResponse = self.processor.process(response.content)

        # Synthesize if there's conversational text
        if processed.conversational_text:
            self.set_state(PipelineState.SPEAKING)
            try:
                audio_bytes = await self.tts.synthesize(processed.conversational_text)
                if not self.tts.is_interrupted:
                    await self.player.play_bytes(audio_bytes)
            except Exception as e:
                logger.error(f"TTS error: {e}")

        total = time.monotonic() - start

        result = TurnResult(
            user_text=text,
            agent_text=processed.conversational_text,
            corrections=processed.corrections,
            new_vocabulary=processed.new_vocabulary,
            latency_llm=total,
            total_latency=total,
        )

        self.set_state(PipelineState.LISTENING)
        return result

    # === Audio capture for microphone input ===

    async def run_microphone_loop(
        self, device: int | None = None, block_duration_ms: int = 60
    ):
        """
        Main microphone capture loop.
        Captures audio from the default microphone and feeds it to the pipeline.

        Args:
            device: Audio device index (None = default)
            block_duration_ms: Duration of each audio block in ms
        """
        import sounddevice as sd

        sample_rate = self.config.sample_rate
        block_size = int(sample_rate * block_duration_ms / 1000)

        logger.info(f"Starting microphone capture: {sample_rate}Hz, "
                     f"block={block_duration_ms}ms ({block_size} samples)")

        queue: asyncio.Queue = asyncio.Queue()

        # Capture the event loop for use in the CFFI audio callback thread
        loop = asyncio.get_running_loop()
        self._loop = loop

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"Audio status: {status}")
            try:
                asyncio.run_coroutine_threadsafe(
                    queue.put(indata.copy().flatten()),
                    loop,
                )
            except Exception:
                pass  # Queue full or loop closing

        try:
            stream = sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                device=device,
                dtype=np.float32,
                blocksize=block_size,
                callback=audio_callback,
            )

            with stream:
                logger.info("Microphone stream started")

                while self._conversation_active:
                    try:
                        audio_chunk = await asyncio.wait_for(
                            queue.get(), timeout=1.0
                        )
                        await self.process_audio_chunk(audio_chunk)
                    except asyncio.TimeoutError:
                        # No audio in 1 second — just continue
                        continue
                    except Exception as e:
                        logger.error(f"Audio loop error: {e}")
                        break

        except Exception as e:
            logger.error(f"Failed to open microphone: {e}")
            self.set_state(PipelineState.ERROR)
            for cb in self._on_error:
                await cb(f"Microphone error: {e}")
        finally:
            logger.info("Microphone loop ended")
            await self.stop()
