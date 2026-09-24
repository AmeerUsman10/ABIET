"""
Language-model client.

ABIET talks to OpenAI's Chat Completions API, which most hosted and local
model servers also implement (Azure OpenAI, Ollama, vLLM, LM Studio, ...).
Point ``OPENAI_BASE_URL`` at such a server to use it instead of OpenAI.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Protocol

import openai

from backend.config import settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """The language model could not produce a usable answer."""


class LLMNotConfigured(LLMError):
    """No AI provider is configured."""


class LLMClient(Protocol):
    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, Any]: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from a model reply, tolerating code fences and surrounding prose."""
    cleaned = _FENCE.sub("", (text or "").strip())
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise LLMError("The AI returned a response that was not valid JSON") from None
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError("The AI returned a response that was not valid JSON") from exc
    if not isinstance(value, dict):
        raise LLMError("The AI returned an unexpected response format")
    return value


class OpenAIChatClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        base_url: str | None = None,
        temperature: float | None = 0.0,
        json_mode: bool = True,
        timeout: float = 60.0,
    ):
        self.model = model
        self.temperature = temperature
        self.json_mode = json_mode
        self._client = openai.OpenAI(
            api_key=api_key or "not-needed", base_url=base_url or None, timeout=timeout, max_retries=2
        )

    def complete_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages}
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise LLMError("The AI provider rejected the API key (check OPENAI_API_KEY)") from exc
        except openai.RateLimitError as exc:
            raise LLMError("The AI provider's rate limit or quota was reached; try again shortly") from exc
        except openai.APITimeoutError as exc:
            raise LLMError("The AI provider took too long to respond") from exc
        except openai.APIConnectionError as exc:
            raise LLMError("Could not reach the AI provider") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"AI provider error ({exc.status_code}): {exc.message}") from exc
        except openai.OpenAIError as exc:
            raise LLMError(f"AI provider error: {exc}") from exc
        if not response.choices:
            raise LLMError("The AI provider returned an empty response")
        return parse_json_object(response.choices[0].message.content or "")


_client: LLMClient | None = None
_client_lock = threading.Lock()


def get_llm() -> LLMClient:
    """FastAPI dependency returning the configured client (overridden in tests)."""
    global _client
    if not settings.ai_configured:
        raise LLMNotConfigured(
            "AI is not configured. Set OPENAI_API_KEY (or OPENAI_BASE_URL for a compatible server) and restart."
        )
    with _client_lock:
        if _client is None:
            _client = OpenAIChatClient(
                api_key=settings.OPENAI_API_KEY,
                model=settings.AI_MODEL,
                base_url=settings.OPENAI_BASE_URL,
                temperature=settings.AI_TEMPERATURE,
                json_mode=settings.AI_JSON_MODE,
                timeout=settings.AI_TIMEOUT_SECONDS,
            )
        return _client
