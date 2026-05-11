"""
Audio playback for the English Coach Agent.
Handles decoding and playing MP3 audio from edge-tts.
Supports barge-in (interrupting speech when user starts talking).
"""

import asyncio
import io
import sys
import threading
from dataclasses import dataclass
from queue import Queue, Empty

import numpy as np
import soundfile as sf

from config.logging_config import setup_logging

logger = setup_logging()


@dataclass
class AudioConfig:
    sample_rate: int = 24000
    channels: int = 1
    device: int | None = None  # None = default output device


class AudioPlayer:
    """
    Plays audio on the system's default output device.
    Supports streaming playback and barge-in (interrupt).
    """

    def __init__(self, config: AudioConfig | None = None):
        self.config = config or AudioConfig()
        self._playing = False
        self._interrupted = False
        self._stream = None
        self._audio_queue: Queue = Queue()
        self._stop_event = threading.Event()
        self._playback_thread: threading.Thread | None = None

    def interrupt(self):
        """Stop current playback immediately (barge-in)."""
        if self._playing:
            self._interrupted = True
            self._stop_event.set()
            logger.debug("Audio playback interrupted")

    async def play_bytes(self, audio_bytes: bytes):
        """
        Decode and play MP3 audio bytes.
        Blocks until playback completes or is interrupted.

        Args:
            audio_bytes: Raw MP3 audio data from edge-tts
        """
        if not audio_bytes:
            return

        # Decode MP3 to PCM using soundfile (requires system libsndfile with mp3 support)
        # Fall back to pydub or ffmpeg if needed
        try:
            audio_data, sample_rate = self._decode_mp3(audio_bytes)
        except Exception as e:
            logger.error(f"MP3 decode failed: {e}")
            return

        await self._play_pcm(audio_data, sample_rate)

    async def play_stream(self, audio_chunks):
        """
        Play audio chunks as they arrive (streaming playback).
        Reduces latency — starts playing before all audio is synthesized.

        Args:
            audio_chunks: Async iterator yielding bytes chunks
        """
        self._playing = True
        self._interrupted = False
        self._stop_event.clear()

        # Accumulate audio while playing
        accumulated = bytearray()

        try:
            async for chunk in audio_chunks:
                if self._interrupted:
                    break
                accumulated.extend(chunk)

            if not self._interrupted and accumulated:
                await self.play_bytes(bytes(accumulated))

        except Exception as e:
            logger.error(f"Stream playback error: {e}")
        finally:
            self._playing = False

    async def _play_pcm(self, audio_data: np.ndarray, sample_rate: int):
        """Play PCM audio data through speakers."""
        import sounddevice as sd

        self._playing = True
        self._interrupted = False
        self._stop_event.clear()

        try:
            loop = asyncio.get_event_loop()

            def _play():
                # We need to check if interrupted during playback
                chunk_size = 1024
                pos = 0
                total = len(audio_data)

                with sd.OutputStream(
                    samplerate=sample_rate,
                    channels=self.config.channels,
                    device=self.config.device,
                    dtype=np.float32,
                ) as stream:
                    while pos < total and not self._stop_event.is_set():
                        end = min(pos + chunk_size, total)
                        chunk = audio_data[pos:end]

                        if audio_data.ndim == 1:
                            chunk = chunk.reshape(-1, 1)

                        stream.write(chunk)
                        pos = end

            await loop.run_in_executor(None, _play)

            logger.debug("Audio playback complete")

        except Exception as e:
            logger.error(f"Audio playback error: {e}")
            raise
        finally:
            self._playing = False

    def _decode_mp3(self, audio_bytes: bytes) -> tuple[np.ndarray, int]:
        """
        Decode MP3 bytes to numpy array.

        Uses soundfile with pydub as fallback for MP3 decoding.
        """
        # Try soundfile first (needs libsndfile with mp3 support)
        try:
            mp3_io = io.BytesIO(audio_bytes)
            audio_data, sample_rate = sf.read(mp3_io, dtype="float32")
            return audio_data, int(sample_rate)
        except Exception:
            pass

        # Fallback: use pydub (requires ffmpeg or libav)
        try:
            from pydub import AudioSegment

            mp3_io = io.BytesIO(audio_bytes)
            segment = AudioSegment.from_file(mp3_io, format="mp3")

            # Convert to numpy array
            samples = np.array(segment.get_array_of_samples(), dtype=np.float32)
            samples = samples / (1 << (8 * segment.sample_width - 1))

            if segment.channels > 1:
                samples = samples.reshape((-1, segment.channels))
                samples = samples.mean(axis=1)  # Convert to mono

            return samples, segment.frame_rate

        except ImportError:
            logger.warning(
                "Neither soundfile (MP3) nor pydub available for MP3 decoding. "
                "Install pydub: pip install pydub"
            )
            raise RuntimeError("No MP3 decoder available")

    def play_sound_file(self, filepath: str):
        """Play a WAV sound file (for UI sounds like listening/thinking indicators)."""
        try:
            audio_data, sample_rate = sf.read(filepath, dtype="float32")
            asyncio.create_task(self._play_pcm(audio_data, sample_rate))
        except Exception as e:
            logger.warning(f"Could not play sound file '{filepath}': {e}")

    @property
    def is_playing(self) -> bool:
        return self._playing

    def close(self):
        """Clean up audio resources."""
        self.interrupt()
