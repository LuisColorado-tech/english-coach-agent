"""
English Coach Agent — Main orchestrator class.
Wires together the full pipeline: STT → LLM → TTS with memory and scheduling.

This is the primary class that starts and manages the agent.
"""

import asyncio
import signal
from datetime import datetime, timezone
from pathlib import Path

from config.settings import (
    DATA_DIR,
    DB_PATH,
    DEEPSEEK_API_KEY,
    WHISPER_MODEL,
    TTS_DEFAULT_VOICE,
)
from config.logging_config import setup_logging
from core.pipeline import Pipeline, PipelineConfig, TurnResult
from core.context_builder import ContextBuilder
from stt.whisper_stt import WhisperSTTService, WhisperConfig
from stt.vad_handler import SileroVADHandler, VADConfig
from llm.deepseek_client import DeepSeekClient
from llm.response_processor import ResponseProcessor
from tts.edge_tts_handler import EdgeTTSService, TTSConfig
from tts.audio_player import AudioPlayer, AudioConfig
from memory.profile_manager import ProfileManager

logger = setup_logging()


class EnglishCoachAgent:
    """
    Main agent orchestrator for the English Coach Agent.

    Manages:
    - Pipeline lifecycle (start, stop, pause, resume)
    - Component initialization
    - System prompt building
    - Session tracking
    - Graceful shutdown
    """

    def __init__(self):
        self.pipeline: Pipeline | None = None
        self._stt: WhisperSTTService | None = None
        self._llm: DeepSeekClient | None = None
        self._tts: EdgeTTSService | None = None
        self._player: AudioPlayer | None = None
        self._vad: SileroVADHandler | None = None
        self._processor: ResponseProcessor | None = None
        self._profile_manager = ProfileManager()
        self._context_builder = ContextBuilder()

        self._session_start: datetime | None = None
        self._total_corrections: int = 0
        self._total_turns: int = 0
        self._topics_covered: list[str] = []
        self._running = False
        self._shutdown_event = asyncio.Event()

        # UI callback hooks
        self._ui_callbacks = {
            "on_state_change": [],
            "on_transcription": [],
            "on_response": [],
            "on_correction": [],
            "on_turn_complete": [],
            "on_error": [],
        }

    # === UI callback registration ===

    def on(self, event: str, callback):
        if event in self._ui_callbacks:
            self._ui_callbacks[event].append(callback)

    async def _emit(self, event: str, *args):
        for cb in self._ui_callbacks.get(event, []):
            try:
                await cb(*args)
            except Exception as e:
                logger.error(f"Callback error ({event}): {e}")

    # === Initialization ===

    async def initialize(self):
        """Initialize all components. Called once at startup."""
        logger.info("========================================")
        logger.info("  English Coach Agent (ECA-1) v1.0.0")
        logger.info("========================================")

        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Initialize STT
        logger.info("Initializing STT (Faster-Whisper)...")
        whisper_config = WhisperConfig(model_size=WHISPER_MODEL)
        self._stt = WhisperSTTService(whisper_config)
        await self._stt.initialize()

        # Initialize LLM
        logger.info("Initializing LLM (DeepSeek)...")
        self._llm = DeepSeekClient()
        await self._llm.initialize()

        # Initialize TTS
        logger.info("Initializing TTS (edge-tts)...")
        tts_config = TTSConfig(voice=TTS_DEFAULT_VOICE)
        self._tts = EdgeTTSService(tts_config)

        # Initialize Audio Player
        logger.info("Initializing audio player...")
        audio_config = AudioConfig()
        self._player = AudioPlayer(audio_config)

        # Initialize VAD
        logger.info("Initializing VAD (Silero)...")
        vad_config = VADConfig()
        self._vad = SileroVADHandler(vad_config)
        await self._vad.initialize()

        # Initialize response processor
        self._processor = ResponseProcessor()

        # Build system prompt from profile
        if self._profile_manager.is_first_run():
            logger.info("First run detected — setup wizard recommended")
            logger.info(f"Run: python setup.py")
        else:
            logger.info(f"Loaded profile: {self._profile_manager.get_summary()}")
        system_prompt = self._build_system_prompt()
        self._llm.set_system_prompt(system_prompt)

        # Create pipeline
        self.pipeline = Pipeline(
            stt_service=self._stt,
            llm_client=self._llm,
            tts_service=self._tts,
            audio_player=self._player,
            vad_handler=self._vad,
            response_processor=self._processor,
        )

        # Wire up pipeline events
        self.pipeline.on_state_change(self._handle_state_change)
        self.pipeline.on_transcription(self._handle_transcription)
        self.pipeline.on_response(self._handle_response)
        self.pipeline.on_correction(self._handle_correction)
        self.pipeline.on_turn_complete(self._handle_turn_complete)
        self.pipeline.on_error(self._handle_error)

        # Initialize session
        self._session_start = datetime.now(timezone.utc)
        self._total_corrections = 0
        self._total_turns = 0

        logger.info("All components initialized successfully")
        logger.info("Agent ready for conversation")

    # === Pipeline event handlers ===

    async def _handle_state_change(self, new_state, old_state):
        await self._emit("on_state_change", new_state, old_state)

    async def _handle_transcription(self, text: str):
        await self._emit("on_transcription", text)

    async def _handle_response(self, processed):
        await self._emit("on_response", processed)

    async def _handle_correction(self, correction):
        self._total_corrections += 1
        await self._emit("on_correction", correction)

    async def _handle_turn_complete(self, result: TurnResult):
        self._total_turns += 1
        self._topics_covered.append(result.user_text[:50])
        await self._emit("on_turn_complete", result)

    async def _handle_error(self, error_msg: str):
        logger.error(f"Pipeline error: {error_msg}")
        await self._emit("on_error", error_msg)

    # === System prompt ===

    def _build_system_prompt(self) -> str:
        """Build the system prompt from user profile via ContextBuilder."""
        return self._context_builder.build()

    def get_profile(self) -> dict:
        """Get the full user profile."""
        return self._profile_manager.to_dict()

    # === Lifecycle ===

    async def start(self, use_microphone: bool = True):
        """
        Start the agent and begin listening.

        Args:
            use_microphone: If True, captures from mic. If False, waits for
                           text input via send_text().
        """
        if self._running:
            logger.warning("Agent is already running")
            return

        await self.initialize()

        if self.pipeline is None:
            logger.error("Pipeline not initialized")
            return

        await self.pipeline.start()

        self._running = True

        if use_microphone:
            await self.pipeline.run_microphone_loop()
        else:
            # Wait for shutdown without mic capture
            await self._shutdown_event.wait()

    async def stop(self):
        """Stop the agent gracefully."""
        logger.info("Shutting down agent...")

        self._running = False
        self._shutdown_event.set()

        if self.pipeline:
            await self.pipeline.stop()

        if self._player:
            self._player.close()

        # Write session summary
        await self._save_session_summary()

        logger.info("Agent shutdown complete")

    def pause(self):
        """Pause the agent (stop listening)."""
        if self.pipeline:
            self.pipeline.pause()

    def resume(self):
        """Resume the agent (start listening again)."""
        if self.pipeline:
            self.pipeline.resume()

    async def send_text(self, text: str):
        """Send text directly to the LLM (bypass mic)."""
        if self.pipeline:
            return await self.pipeline.send_text(text)
        return None

    async def _save_session_summary(self):
        """Save session metadata to disk."""
        if not self._session_start:
            return

        session_data = {
            "started_at": self._session_start.isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "total_turns": self._total_turns,
            "total_corrections": self._total_corrections,
            "topics_covered": self._topics_covered[-10:],  # Last 10 topics
        }

        # Save to JSON for now (will migrate to SQLite in Phase 2)
        sessions_file = DATA_DIR / "session_last.json"
        try:
            sessions_file.write_text(json.dumps(session_data, indent=2))
            logger.info(f"Session summary saved to {sessions_file}")
        except Exception as e:
            logger.warning(f"Could not save session summary: {e}")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict:
        return {
            "total_turns": self._total_turns,
            "total_corrections": self._total_corrections,
            "session_start": self._session_start.isoformat() if self._session_start else None,
            "state": self.pipeline.state.name if self.pipeline else "IDLE",
        }
