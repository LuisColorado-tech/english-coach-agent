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
        if self._model is not None:
            try:
                # silero-vad expects 1D float32 numpy array
                audio_1d = audio_frame.astype(np.float32)
                if audio_1d.ndim > 1:
                    audio_1d = audio_1d.mean(axis=1)

                prob = float(self._model(audio_1d, self.config.sample_rate))
            except Exception as e:
                logger.debug(f"Silero VAD failed, using energy fallback: {e}")
                prob = await self._energy_vad(audio_frame)
        else:
            prob = await self._energy_vad(audio_frame)

        self._speech_prob = prob

        # Log every ~20 frames to avoid spam
        if not hasattr(self, '_frame_counter'):
            self._frame_counter = 0
        self._frame_counter += 1
        if self._frame_counter % 20 == 0:
            logger.debug(f"VAD prob: {prob:.3f} | threshold: {self.config.threshold} | "
                         f"state: {self._state.name} | speaking: {self.is_speaking}")

        for cb in self._on_vad_prob:
            try:
                r = cb(prob)
                if r is not None and asyncio.iscoroutine(r):
                    await r
            except Exception:
                pass

        is_speech = prob >= self.config.threshold

        if is_speech:
            self._speech_frames += 1
            self._silence_frames = 0

            if (
                self._state != VADState.SPEECH
                and self._speech_frames >= self._min_speech_frames
            ):
                self._state = VADState.SPEECH
                logger.debug("VAD: speech START detected")
                for cb in self._on_speech_start:
                    try:
                        r = cb()
                        if r is not None and asyncio.iscoroutine(r):
                            await r
                    except Exception:
                        pass
        else:
            self._silence_frames += 1

            if self._state == VADState.SPEECH:
                self._speech_frames += 1

            if (
                self._state == VADState.SPEECH
                and self._silence_frames >= self._silence_threshold_frames
                and self._speech_frames >= self._speech_pad_frames
            ):
                self._state = VADState.SILENCE
                self._speech_frames = 0
                logger.debug("VAD: speech END detected")
                for cb in self._on_speech_end:
                    try:
                        r = cb()
                        if r is not None and asyncio.iscoroutine(r):
                            await r
                    except Exception:
                        pass

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
