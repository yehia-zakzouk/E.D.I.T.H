"""OpenAI provider — talks to OpenAI's Chat Completions API.

Reads configuration from ``llm_config`` which is populated via
``EDITH_LLM__`` environment variables or .env file.

Environment variables
--------------------
    EDITH_LLM__PROVIDER=openai
    EDITH_LLM__OPENAI_API_KEY=sk-...
    EDITH_LLM__OPENAI_MODEL=gpt-4o-mini
"""

from __future__ import annotations

import os
from typing import Any, Iterator, Optional

from openai import OpenAI, APIError, RateLimitError

from app.llm.config import llm_config
from app.llm.providers.base import BaseProvider
from app.core.config import logger


class OpenAIProvider(BaseProvider):
    """Provider that talks to OpenAI's Chat Completions API.

    API Key resolution order:
    1. Explicitly passed to constructor
    2. ``llm_config.openai_api_key`` (from EDITH_LLM__OPENAI_API_KEY)
    3. ``OPENAI_API_KEY`` environment variable

    The OpenAI client is created lazily to avoid crashes when no
    API key is configured at import time.
    """

    def __init__(self, *, api_key: Optional[str] = None, model: Optional[str] = None):
        env_key = os.environ.get("OPENAI_API_KEY") or ""
        self._api_key = api_key or llm_config.openai_api_key or env_key
        self._model = model or llm_config.openai_model or "gpt-4o-mini"
        self._base_url = None
        self._client: Optional[OpenAI] = None

        if not self._api_key:
            logger.warning(
                "OpenAIProvider: no API key set — set OPENAI_API_KEY "
                "or EDITH_LLM__OPENAI_API_KEY"
            )

    def _get_client(self) -> OpenAI:
        """Lazy-create the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    # ── Core API ────────────────────────────────────────────────────

    def chat(self, messages: list[dict], **kwargs) -> str:
        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=kwargs.get("temperature", llm_config.temperature),
                max_tokens=kwargs.get("max_tokens", llm_config.max_tokens),
                stream=False,
            )
            content = response.choices[0].message.content or ""
            logger.debug("OpenAIProvider.chat: %d chars returned", len(content))
            return content
        except RateLimitError:
            logger.error("OpenAI rate limit exceeded")
            return "The AI service is currently rate-limited. Please wait and try again."
        except APIError as e:
            logger.error("OpenAI API error: %s", e)
            return f"AI service error: {e}"
        except Exception as e:
            logger.exception("Unexpected OpenAI error")
            return f"Unexpected error: {e}"

    def stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        try:
            client = self._get_client()
            stream = client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=kwargs.get("temperature", llm_config.temperature),
                max_tokens=kwargs.get("max_tokens", llm_config.max_tokens),
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield delta
        except Exception as e:
            logger.exception("Error in OpenAI stream")
            yield f"Error: {e}"

    # ── Management ──────────────────────────────────────────────────

    def list_models(self) -> list[str]:
        try:
            client = self._get_client()
            models = client.models.list()
            chat_models = [
                m.id for m in models
                if m.id.startswith(("gpt-", "o1-", "o3-"))
            ]
            return sorted(chat_models)
        except Exception as e:
            logger.warning("OpenAIProvider: failed to list models: %s", e)
            return [self._model]

    def health_check(self) -> bool:
        try:
            client = self._get_client()
            client.models.list()
            return True
        except Exception:
            return False

    def set_model(self, model_name: str) -> None:
        logger.info("OpenAIProvider: switched to model %s", model_name)
        self._model = model_name

    # ── Properties ──────────────────────────────────────────────────

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def token_limit(self) -> int:
        limits = {
            "gpt-4o": 128_000,
            "gpt-4o-mini": 128_000,
            "gpt-4-turbo": 128_000,
            "gpt-3.5-turbo": 16_385,
            "o1": 200_000,
            "o3": 200_000,
        }
        return limits.get(self._model, 128_000)

    @property
    def model_info(self) -> dict:
        return {
            "model": self._model,
            "provider": "openai",
            "token_limit": self.token_limit,
            "running": "cloud",
            "api_key_set": bool(self._api_key),
        }
