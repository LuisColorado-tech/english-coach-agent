"""
DeepSeek chat client using OpenAI-compatible SDK.
Handles multi-turn conversations, streaming, retry with backoff.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

from openai import AsyncOpenAI

from config.settings import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    DEEPSEEK_TEMPERATURE,
    DEEPSEEK_MAX_TOKENS,
    DEEPSEEK_MAX_HISTORY_TURNS,
    DEEPSEEK_RETRY_ATTEMPTS,
    DEEPSEEK_RETRY_BACKOFF,
)
from config.logging_config import setup_logging

logger = setup_logging()


@dataclass
class ChatMessage:
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: dict | None = None
    finish_reason: str = "stop"
    latency_seconds: float = 0.0


class DeepSeekClient:
    """
    Async client for DeepSeek Chat API.
    Compatible with OpenAI SDK — only base_url and api_key differ.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_history_turns: int | None = None,
    ):
        self.api_key = api_key or DEEPSEEK_API_KEY
        self.base_url = base_url or DEEPSEEK_BASE_URL
        self.model = model or DEEPSEEK_MODEL
        self.temperature = temperature if temperature is not None else DEEPSEEK_TEMPERATURE
        self.max_tokens = max_tokens or DEEPSEEK_MAX_TOKENS
        self.max_history_turns = max_history_turns or DEEPSEEK_MAX_HISTORY_TURNS

        self._client: AsyncOpenAI | None = None
        self._conversation_history: list[dict] = []
        self._system_prompt: str | None = None

    async def initialize(self):
        """Create the async OpenAI client pointing to DeepSeek."""
        if not self.api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY is not set. "
                "Add it to your .env file or environment variables."
            )

        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
        )
        logger.info(f"DeepSeek client initialized (model: {self.model})")

    def set_system_prompt(self, prompt: str):
        """Set the system prompt used for every request."""
        self._system_prompt = prompt

    def add_user_message(self, content: str):
        """Add a user message to conversation history."""
        self._conversation_history.append({"role": "user", "content": content})
        self._trim_history()

    def add_assistant_message(self, content: str):
        """Add an assistant (agent) message to conversation history."""
        self._conversation_history.append({"role": "assistant", "content": content})
        self._trim_history()

    def _trim_history(self):
        """Keep conversation history within configured turn limit."""
        # Each turn = 1 user + 1 assistant message = 2 messages
        max_messages = self.max_history_turns * 2
        if len(self._conversation_history) > max_messages:
            self._conversation_history = self._conversation_history[-max_messages:]

    def _build_messages(self) -> list[dict]:
        """Build the full message list including system prompt and history."""
        messages = []

        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})

        messages.extend(self._conversation_history)

        return messages

    async def chat(self, user_message: str) -> LLMResponse:
        """
        Send a message and get complete response.
        Non-streaming mode. Returns full response.
        """
        self.add_user_message(user_message)

        start_time = time.monotonic()

        for attempt in range(DEEPSEEK_RETRY_ATTEMPTS):
            try:
                response = await self._client.chat.completions.create(
                    model=self.model,
                    messages=self._build_messages(),
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=False,
                )

                content = response.choices[0].message.content or ""
                self.add_assistant_message(content)

                elapsed = time.monotonic() - start_time
                logger.debug(f"LLM response ({elapsed:.2f}s): '{content[:80]}...'")

                return LLMResponse(
                    content=content,
                    model=response.model,
                    usage=response.usage.model_dump() if response.usage else None,
                    finish_reason=response.choices[0].finish_reason or "stop",
                    latency_seconds=elapsed,
                )

            except Exception as e:
                logger.warning(f"DeepSeek API error (attempt {attempt + 1}): {e}")
                if attempt < DEEPSEEK_RETRY_ATTEMPTS - 1:
                    delay = DEEPSEEK_RETRY_BACKOFF[attempt]
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All retry attempts failed: {e}")
                    raise

        # Should not reach here, but provide fallback
        raise RuntimeError("DeepSeek API request failed after all retries")

    async def chat_stream(self, user_message: str) -> AsyncIterator[str]:
        """
        Send a message and yield response chunks as they arrive.
        Streaming mode — reduces perceived latency.
        """
        self.add_user_message(user_message)

        full_response: list[str] = []
        start_time = time.monotonic()

        for attempt in range(DEEPSEEK_RETRY_ATTEMPTS):
            try:
                stream = await self._client.chat.completions.create(
                    model=self.model,
                    messages=self._build_messages(),
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    stream=True,
                )

                async for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full_response.append(token)
                        yield token

                break  # Success, exit retry loop

            except Exception as e:
                logger.warning(f"DeepSeek streaming error (attempt {attempt + 1}): {e}")
                if attempt < DEEPSEEK_RETRY_ATTEMPTS - 1:
                    delay = DEEPSEEK_RETRY_BACKOFF[attempt]
                    await asyncio.sleep(delay)
                    full_response.clear()
                else:
                    logger.error(f"All streaming retries failed: {e}")
                    raise

        # Store complete response in history
        full_text = "".join(full_response)
        self.add_assistant_message(full_text)

        elapsed = time.monotonic() - start_time
        logger.debug(f"LLM streaming complete ({elapsed:.2f}s): '{full_text[:80]}...'")

    def clear_history(self):
        """Clear conversation history but keep system prompt."""
        self._conversation_history.clear()
        logger.debug("Conversation history cleared")

    def reset(self):
        """Full reset — clear history and system prompt."""
        self._conversation_history.clear()
        self._system_prompt = None

    @property
    def history_turn_count(self) -> int:
        return len(self._conversation_history) // 2

    @property
    def is_ready(self) -> bool:
        return self._client is not None and bool(self.api_key)
