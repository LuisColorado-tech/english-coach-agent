"""
edge-tts wrapper for the English Coach Agent.
Provides text-to-speech synthesis using Microsoft Edge's free TTS.
"""

import asyncio
import io
from dataclasses import dataclass

import edge_tts

from config.settings import (
    TTS_DEFAULT_VOICE,
    TTS_RATE,
    TTS_PITCH,
    TTS_VOLUME,
)
from config.logging_config import setup_logging

logger = setup_logging()


@dataclass
class TTSConfig:
    voice: str = TTS_DEFAULT_VOICE
    rate: str = TTS_RATE
    pitch: str = TTS_PITCH
    volume: str = TTS_VOLUME
    output_format: str = "audio-24khz-48kbitrate-mono-mp3"


@dataclass
class TTSVoice:
    short_name: str
    locale: str
    gender: str
    friendly_name: str


class EdgeTTSService:
    """
    Async text-to-speech service using Microsoft Edge TTS.
    Free, no limits, natural neural voices.
    """

    def __init__(self, config: TTSConfig | None = None):
        self.config = config or TTSConfig()
        self._interrupted = False
        self._synthesizing = False

    def interrupt(self):
        """Signal the current synthesis to stop. Enables barge-in."""
        if self._synthesizing:
            self._interrupted = True
            logger.debug("TTS interrupted by user")

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
    ) -> bytes:
        """
        Synthesize text to audio bytes (MP3 format).

        Args:
            text: The text to synthesize
            voice: Optional voice to use (overrides default)

        Returns:
            MP3 audio bytes

        Raises:
            edge_tts.Exceptions on network/synthesis errors
        """
        self._synthesizing = True
        self._interrupted = False

        selected_voice = voice or self.config.voice

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=selected_voice,
                rate=self.config.rate,
                pitch=self.config.pitch,
                volume=self.config.volume,
            )

            audio_chunks: list[bytes] = []

            async for chunk in communicate.stream():
                if self._interrupted:
                    logger.debug("TTS synthesis interrupted mid-stream")
                    break

                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])

            full_audio = b"".join(audio_chunks)
            logger.debug(f"TTS synthesized {len(full_audio)} bytes of audio")

            return full_audio

        except Exception as e:
            logger.error(f"edge-tts synthesis error: {e}")
            raise
        finally:
            self._synthesizing = False

    async def synthesize_stream(
        self,
        text: str,
        voice: str | None = None,
    ):
        """
        Synthesize text and yield audio chunks as they become available.
        Useful for reducing latency — start playback before synthesis finishes.

        Args:
            text: Text to synthesize
            voice: Optional voice override

        Yields:
            bytes: MP3 audio chunks
        """
        self._synthesizing = True
        self._interrupted = False

        selected_voice = voice or self.config.voice

        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=selected_voice,
                rate=self.config.rate,
                pitch=self.config.pitch,
                volume=self.config.volume,
            )

            async for chunk in communicate.stream():
                if self._interrupted:
                    break

                if chunk["type"] == "audio":
                    yield chunk["data"]

        except Exception as e:
            logger.error(f"edge-tts streaming error: {e}")
            raise
        finally:
            self._synthesizing = False

    async def list_voices(self) -> list[TTSVoice]:
        """List available Microsoft Edge TTS voices."""
        voices = await edge_tts.list_voices()

        result = []
        for v in voices:
            if v["Locale"].startswith("en"):
                result.append(
                    TTSVoice(
                        short_name=v["ShortName"],
                        locale=v["Locale"],
                        gender=v.get("Gender", "Unknown"),
                        friendly_name=v.get("FriendlyName", v["ShortName"]),
                    )
                )

        return result

    async def preview_voice(self, voice: str | None = None) -> bytes:
        """Generate a short preview of a specific voice."""
        preview_text = "Hello! I'm your English coach. Let's practice together."
        return await self.synthesize(preview_text, voice=voice)

    @property
    def is_synthesizing(self) -> bool:
        return self._synthesizing

    @property
    def is_interrupted(self) -> bool:
        return self._interrupted

    def reset(self):
        self._interrupted = False
        self._synthesizing = False
