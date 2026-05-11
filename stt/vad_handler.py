"""
Silero VAD handler for Pipecat pipeline.
Configures and wraps Silero Voice Activity Detection.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum, auto

import numpy as np

from config.settings import VAD_THRESHOLD, VAD_FRAME_DURATION_MS, STT_SAMPLE_RATE
from config.logging_config import setup_logging

logger = setup_logging()


class VADState(Enum):
    SILENCE = auto()
    SPEECH = auto()
    TRANSITIONING = auto()


@dataclass
class VADConfig:
    threshold: float = VAD_THRESHOLD
    frame_duration_ms: int = VAD_FRAME_DURATION_MS
    sample_rate: int = STT_SAMPLE_RATE
    silence_trigger_ms: int = 800
    speech_pad_ms: int = 200
    min_speech_duration_ms: int = 250


class SileroVADHandler:
    """
    Wraps Silero VAD for use in the pipeline.
    Detects speech start/end events from raw PCM audio frames.
    """

    def __init__(self, config: VADConfig | None = None):
        self.config = config or VADConfig()
        self._model = None
        self._state = VADState.SILENCE
        self._speech_prob = 0.0
        self._silence_frames = 0
        self._speech_frames = 0
        self._on_speech_start: list[callable] = []
        self._on_speech_end: list[callable] = []
        self._on_vad_prob: list[callable] = []

        self._frames_per_check = int(
            self.config.sample_rate
            * self.config.frame_duration_ms
            / 1000
        )
        self._silence_threshold_frames = int(
            self.config.silence_trigger_ms / self.config.frame_duration_ms
        )
        self._min_speech_frames = int(
            self.config.min_speech_duration_ms / self.config.frame_duration_ms
        )
        self._speech_pad_frames = int(
            self.config.speech_pad_ms / self.config.frame_duration_ms
        )

    async def initialize(self):
        try:
            from silero_vad import load_silero_vad, read_audio

            self._model = load_silero_vad(onnx=True)
            logger.info("Silero VAD model loaded successfully")
        except ImportError:
            logger.warning(
                "silero_vad not available. Install with: pip install silero-vad. "
                "VAD will use energy-based detection as fallback."
            )
            self._model = None

    def on_speech_start(self, callback: callable):
        self._on_speech_start.append(callback)

    def on_speech_end(self, callback: callable):
        self._on_speech_end.append(callback)

    def on_vad_prob(self, callback: callable):
        self._on_vad_prob.append(callback)

    async def _energy_vad(self, audio_frame: np.ndarray) -> float:
        """Fallback energy-based VAD when Silero is not available."""
        if audio_frame.ndim > 1:
            audio_frame = audio_frame.mean(axis=1)

        energy = np.sqrt(np.mean(audio_frame.astype(np.float32) ** 2))

        # Normalize to [0, 1] range with logarithmic scaling
        prob = min(1.0, max(0.0, (np.log10(max(energy, 1e-10)) + 5) / 5))
        return float(prob)

    async def process_audio(self, audio_frame: np.ndarray) -> VADState:
        """
        Process an audio frame and return current VAD state.
        Updates internal state machine.
        """
        if self._model is not None:
            try:
                if audio_frame.ndim == 1:
                    audio_frame = audio_frame.reshape(1, -1)

                prob = float(self._model(audio_frame, self.config.sample_rate))
            except Exception:
                prob = await self._energy_vad(audio_frame)
        else:
            prob = await self._energy_vad(audio_frame)

        self._speech_prob = prob

        for cb in self._on_vad_prob:
            await cb(prob)

        is_speech = prob >= self.config.threshold

        if is_speech:
            self._speech_frames += 1
            self._silence_frames = 0

            if (
                self._state != VADState.SPEECH
                and self._speech_frames >= self._min_speech_frames
            ):
                self._state = VADState.SPEECH
                for cb in self._on_speech_start:
                    await cb()
        else:
            self._silence_frames += 1

            if self._state == VADState.SPEECH:
                self._speech_frames += 1  # Continue counting for padding

            if (
                self._state == VADState.SPEECH
                and self._silence_frames >= self._silence_threshold_frames
                and self._speech_frames >= self._speech_pad_frames
            ):
                self._state = VADState.SILENCE
                self._speech_frames = 0
                for cb in self._on_speech_end:
                    await cb()

        return self._state

    @property
    def state(self) -> VADState:
        return self._state

    @property
    def speech_probability(self) -> float:
        return self._speech_prob

    @property
    def is_speaking(self) -> bool:
        return self._state == VADState.SPEECH

    def reset(self):
        self._state = VADState.SILENCE
        self._speech_prob = 0.0
        self._silence_frames = 0
        self._speech_frames = 0
