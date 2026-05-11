"""
Faster-Whisper STT wrapper for the English Coach Agent.
Provides speech-to-text using faster-whisper running locally on CPU.
Integrates with Pipecat pipeline as an audio-to-text service.
"""

import asyncio
import io
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from config.settings import (
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    STT_SAMPLE_RATE,
)
from config.logging_config import setup_logging

logger = setup_logging()


@dataclass
class WhisperConfig:
    model_size: str = WHISPER_MODEL
    device: str = WHISPER_DEVICE
    compute_type: str = WHISPER_COMPUTE_TYPE
    language: str = "en"
    beam_size: int = 5
    vad_filter: bool = True
    vad_threshold: float = 0.5
    min_silence_duration_ms: int = 500
    initial_prompt: str | None = None


@dataclass
class TranscriptionResult:
    text: str
    segments: list[dict] = field(default_factory=list)
    language: str = "en"
    duration_seconds: float = 0.0
    confidence: float = 0.0


class WhisperSTTService:
    """
    Wraps faster-whisper for real-time speech transcription.
    Designed to be called from the Pipecat pipeline.
    """

    def __init__(self, config: WhisperConfig | None = None):
        self.config = config or WhisperConfig()
        self._model = None
        self._is_ready = False
        self._loaded_model_size: str | None = None

    async def initialize(self):
        """Load the faster-whisper model. Called once at startup."""
        try:
            from faster_whisper import WhisperModel

            logger.info(
                f"Loading faster-whisper model '{self.config.model_size}' "
                f"on {self.config.device} ({self.config.compute_type})..."
            )

            loop = asyncio.get_event_loop()
            self._model = await loop.run_in_executor(
                None,
                lambda: WhisperModel(
                    self.config.model_size,
                    device=self.config.device,
                    compute_type=self.config.compute_type,
                ),
            )

            self._loaded_model_size = self.config.model_size
            self._is_ready = True
            logger.info("faster-whisper model loaded successfully")

        except ImportError:
            logger.warning(
                "faster-whisper not available. Install with: pip install faster-whisper. "
                "Falling back to SpeechRecognition + Google STT."
            )
            self._is_ready = False

    async def transcribe(
        self,
        audio_data: np.ndarray,
        initial_prompt: str | None = None,
    ) -> TranscriptionResult:
        """
        Transcribe PCM audio data to English text.

        Args:
            audio_data: float32 numpy array, shape (num_samples,) at 16kHz mono
            initial_prompt: Optional text hint to guide transcription

        Returns:
            TranscriptionResult with transcribed text and metadata
        """
        if not self._is_ready or self._model is None:
            return await self._fallback_transcribe(audio_data)

        start_time = time.monotonic()

        try:
            loop = asyncio.get_event_loop()

            segments_result = []
            full_text_parts = []

            # Convert numpy array to the format faster-whisper expects
            segments, info = await loop.run_in_executor(
                None,
                lambda: self._model.transcribe(
                    audio_data.astype(np.float32),
                    language=self.config.language,
                    beam_size=self.config.beam_size,
                    vad_filter=self.config.vad_filter,
                    vad_parameters={
                        "threshold": self.config.vad_threshold,
                        "min_silence_duration_ms": self.config.min_silence_duration_ms,
                    },
                    initial_prompt=initial_prompt or self.config.initial_prompt,
                ),
            )

            # faster-whisper returns a generator for segments
            for segment in segments:
                full_text_parts.append(segment.text.strip())
                segments_result.append(
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text.strip(),
                    }
                )

            full_text = " ".join(full_text_parts).strip()
            elapsed = time.monotonic() - start_time

            logger.debug(
                f"Transcription ({elapsed:.2f}s): '{full_text[:80]}...' "
                f"lang={info.language} prob={info.language_probability:.2f}"
            )

            return TranscriptionResult(
                text=full_text,
                segments=segments_result,
                language=info.language,
                duration_seconds=elapsed,
                confidence=info.language_probability,
            )

        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return await self._fallback_transcribe(audio_data)

    async def _fallback_transcribe(
        self, audio_data: np.ndarray
    ) -> TranscriptionResult:
        """Fallback using SpeechRecognition + Google STT."""
        try:
            import speech_recognition as sr
        except ImportError:
            logger.error(
                "Neither faster-whisper nor SpeechRecognition available. "
                "Cannot transcribe audio."
            )
            return TranscriptionResult(
                text="",
                segments=[],
                language="en",
                duration_seconds=0.0,
            )

        start_time = time.monotonic()

        try:
            loop = asyncio.get_event_loop()

            def _sr_transcribe():
                recognizer = sr.Recognizer()

                # Convert numpy float32 [-1,1] to 16-bit PCM WAV bytes
                audio_int16 = (audio_data * 32767).astype(np.int16)

                # Write to WAV buffer
                wav_buffer = io.BytesIO()
                sf.write(wav_buffer, audio_int16, STT_SAMPLE_RATE, format="WAV")
                wav_buffer.seek(0)

                with sr.AudioFile(wav_buffer) as source:
                    audio = recognizer.record(source)

                return recognizer.recognize_google(audio, language="en-US")

            text = await loop.run_in_executor(None, _sr_transcribe)
            elapsed = time.monotonic() - start_time

            logger.debug(f"Fallback transcription ({elapsed:.2f}s): '{text[:80]}'")

            return TranscriptionResult(
                text=text.strip(),
                segments=[],
                language="en",
                duration_seconds=elapsed,
            )

        except Exception as e:
            logger.error(f"Fallback transcription failed: {e}")
            return TranscriptionResult(
                text="",
                segments=[],
                language="en",
                duration_seconds=0.0,
            )

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def model_size(self) -> str | None:
        return self._loaded_model_size
