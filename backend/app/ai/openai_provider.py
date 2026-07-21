"""OpenAI provider that uses the Responses API.

Reads configuration from ``config.ai`` (AISettings) which can be populated
via environment variables with the ``EDITH_`` prefix:

    EDITH_AI__API_KEY  = "sk-…"
    EDITH_AI__MODEL    = "gpt-4o-mini"
"""

from __future__ import annotations

import os
import json
from typing import Any, Iterator, Optional

from openai import OpenAI, APIError, RateLimitError

from app.core.config import config, logger
from app.ai.provider import BaseProvider, registry


class OpenAIProvider(BaseProvider):
    """Provider that talks to OpenAI's Responses API (chat completions).

    API Key resolution order:
    1. ``api_key`` passed to the constructor
    2. ``config.ai.api_key`` (from EDITH_AI__ env vars / .env)
    3. ``OPENAI_API_KEY`` environment variable
    """

    def __init__(self, *, api_key: Optional[str] = None, model: Optional[str] = None):
        # Try env var as a final fallback
        env_key = os.environ.get("OPENAI_API_KEY") or ""
        self._api_key = api_key or config.ai.api_key or env_key
        self._model = model or config.ai.model or "gpt-4o-mini"

        if not self._api_key:
            logger.warning(
                "OpenAIProvider: no API key set — set OPENAI_API_KEY, "
                "EDITH_AI__API_KEY, or config.ai.api_key"
            )

        self._client = OpenAI(api_key=self._api_key)

    # ------------------------------------------------------------------
    # BaseProvider interface
    # ------------------------------------------------------------------

    def ask(self, prompt: str, **kwargs) -> str:
        """Send a prompt and return the full text response."""
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", config.ai.temperature),
                max_tokens=kwargs.get("max_tokens", config.ai.max_tokens),
                stream=False,
            )
            content = response.choices[0].message.content or ""
            logger.debug("OpenAIProvider.ask: %d chars returned", len(content))
            return content
        except RateLimitError:
            logger.error("OpenAI rate limit exceeded — try again later or reduce request rate")
            return "I'm sorry, but the AI service is currently rate-limited. Please wait a moment and try again."
        except APIError as e:
            logger.error("OpenAI API error: %s", e)
            return f"I'm sorry, but the AI service returned an error: {e}. Please try again later."
        except Exception as e:
            logger.exception("Unexpected error calling OpenAI")
            return f"An unexpected error occurred while contacting the AI service: {e}"

    def ask_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        """Send a prompt and yield response chunks as they arrive."""
        try:
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", config.ai.temperature),
                max_tokens=kwargs.get("max_tokens", config.ai.max_tokens),
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta
        except Exception as e:
            logger.exception("Error in OpenAI stream")
            yield f"Error: {e}"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def token_limit(self) -> int:
        # Conservative estimates per model family
        limits = {
            "gpt-4o": 128_000,
            "gpt-4o-mini": 128_000,
            "gpt-4-turbo": 128_000,
            "gpt-3.5-turbo": 16_385,
        }
        return limits.get(self._model, 128_000)

    def count_tokens(self, text: str) -> int:
        """Rough token estimate (4 chars ≈ 1 token)."""
        return len(text) // 4


# Register so ProviderRegistry can discover this backend
registry.register("openai", OpenAIProvider)
