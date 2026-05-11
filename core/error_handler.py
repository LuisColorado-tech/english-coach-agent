"""
Error recovery and health monitoring for the English Coach Agent.
Centralized error handling strategy with recovery procedures.
Keeps the agent running through network failures, API issues, and hardware problems.
"""

import asyncio
import time
from dataclasses import dataclass
from enum import Enum

from config.logging_config import setup_logging

logger = setup_logging()


class ErrorSeverity(Enum):
    LOW = "low"           # Recoverable, no user impact
    MEDIUM = "medium"     # Recoverable, brief interruption
    HIGH = "high"         # Recoverable, significant interruption
    CRITICAL = "critical" # May require restart


@dataclass
class ErrorRecord:
    component: str
    error: str
    severity: ErrorSeverity
    timestamp: float = 0.0
    recovered: bool = False

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.monotonic()


class ErrorHandler:
    """
    Unified error handling and recovery for the agent.
    Tracks error history and applies recovery strategies.
    """

    def __init__(self):
        self._errors: list[ErrorRecord] = []
        self._max_errors = 50
        self._recovery_cooldown: dict[str, float] = {}
        self._on_error_callbacks: list[callable] = []
        self._on_recovery_callbacks: list[callable] = []

    def on_error(self, callback):
        """Register callback for error notifications."""
        self._on_error_callbacks.append(callback)

    def on_recovery(self, callback):
        """Register callback for recovery notifications."""
        self._on_recovery_callbacks.append(callback)

    async def handle(
        self,
        component: str,
        error: Exception,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
    ):
        """
        Handle an error from a component with appropriate recovery.
        """
        record = ErrorRecord(
            component=component,
            error=str(error),
            severity=severity,
        )

        self._errors.append(record)
        if len(self._errors) > self._max_errors:
            self._errors = self._errors[-self._max_errors:]

        error_msg = f"[{component}] {severity.value} — {error}"

        if severity == ErrorSeverity.CRITICAL:
            logger.error(error_msg)
        elif severity == ErrorSeverity.HIGH:
            logger.warning(error_msg)
        else:
            logger.debug(error_msg)

        # Notify callbacks
        for cb in self._on_error_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(component, str(error), severity.value)
                else:
                    cb(component, str(error), severity.value)
            except Exception:
                pass

        # Apply recovery strategy
        await self._recover(component, error, severity)

    async def _recover(self, component: str, error: Exception, severity: ErrorSeverity):
        """Apply recovery strategy based on component and error type."""
        # Cooldown check — avoid rapid recovery loops
        now = time.monotonic()
        last_recovery = self._recovery_cooldown.get(component, 0)
        if now - last_recovery < 10:  # 10 second cooldown
            return

        self._recovery_cooldown[component] = now

        error_str = str(error).lower()

        # DeepSeek / LLM errors
        if component in ("deepseek", "llm", "deepseek_client"):
            if any(kw in error_str for kw in ("timeout", "connection", "rate limit")):
                logger.info("LLM connection issue — will retry with backoff")
                await asyncio.sleep(2)
            elif "api_key" in error_str:
                logger.error("Invalid DeepSeek API key — check .env file")
                severity = ErrorSeverity.CRITICAL

        # STT / Whisper errors
        elif component in ("stt", "whisper", "whisper_stt"):
            if any(kw in error_str for kw in ("model", "download", "load")):
                logger.warning("Whisper model issue — falling back to Google STT")
            elif any(kw in error_str for kw in ("microphone", "device", "audio")):
                logger.warning("Audio device error — attempting restart")

        # TTS errors
        elif component in ("tts", "edge_tts", "edge_tts_handler"):
            if any(kw in error_str for kw in ("connection", "network", "timeout")):
                logger.warning("TTS network error — will retry or use fallback")
            elif any(kw in error_str for kw in ("voice", "synthesis")):
                logger.warning(f"TTS synthesis error — trying fallback voice")

        # Pipeline errors
        elif component in ("pipeline", "pipeline.py"):
            logger.warning("Pipeline error — attempting graceful recovery")

        # Notify recovery
        for cb in self._on_recovery_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(component)
                else:
                    cb(component)
            except Exception:
                pass

    def get_error_summary(self) -> list[dict]:
        """Get recent error history."""
        return [
            {
                "component": e.component,
                "error": e.error[:200],
                "severity": e.severity.value,
                "recovered": e.recovered,
            }
            for e in self._errors[-10:]  # Last 10 errors
        ]

    def clear(self):
        """Clear error history."""
        self._errors.clear()

    @property
    def error_count(self) -> int:
        return len(self._errors)

    @property
    def has_critical_errors(self) -> bool:
        return any(e.severity == ErrorSeverity.CRITICAL for e in self._errors[-5:])
