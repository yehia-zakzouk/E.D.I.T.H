"""Ollama provider — talks to Ollama's OpenAI-compatible API.

Uses the OpenAI SDK with a custom base_url pointing at Ollama's
local endpoint. This means EDITH can run completely offline with
local models like Qwen2.5-Coder, DeepSeek, or Llama.

Environment variables
--------------------
    EDITH_LLM__PROVIDER=ollama
    EDITH_LLM__OLLAMA_HOST=http://localhost:11434/v1
    EDITH_LLM__OLLAMA_MODEL=qwen2.5-coder:14b
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterator, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

from openai import OpenAI, APIError

from app.llm.config import llm_config
from app.llm.providers.base import BaseProvider
from app.core.config import logger


class OllamaProvider(BaseProvider):
    """Provider that talks to a local Ollama instance via its OpenAI-compatible API.

    The Ollama API is OpenAI-compatible when accessed at ``/v1``, so we
    can use the OpenAI SDK with a custom ``base_url`` and ``api_key="ollama"``.
    """

    def __init__(self, *, host: Optional[str] = None, model: Optional[str] = None):
        self._host = (host or llm_config.ollama_host).rstrip("/")
        self._model = model or llm_config.ollama_model or "qwen2.5-coder:14b"

        # Extract the base URL (strip /v1 if present)
        base_url = self._host
        if not base_url.endswith("/v1"):
            # Ensure we append /v1 for the OpenAI client
            self._api_base = base_url.rstrip("/") + "/v1"
        else:
            self._api_base = base_url

        # Raw host for non-OpenAI API calls (like /api/tags)
        self._raw_host = base_url.replace("/v1", "").rstrip("/")

        logger.info(
            "OllamaProvider: host=%s model=%s",
            self._api_base,
            self._model,
        )

        # Initialize the OpenAI-compatible client
        self._client = OpenAI(
            base_url=self._api_base,
            api_key="ollama",  # Required by the SDK but ignored by Ollama
        )

    # ── Core API ────────────────────────────────────────────────────

    def chat(self, messages: list[dict], **kwargs) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=kwargs.get("temperature", llm_config.temperature),
                max_tokens=kwargs.get("max_tokens", llm_config.max_tokens),
                stream=False,
            )
            content = response.choices[0].message.content or ""
            logger.debug("OllamaProvider.chat: %d chars returned", len(content))
            return content
        except APIError as e:
            logger.error("Ollama API error: %s", e)
            return f"Ollama error: {e}"
        except Exception as e:
            logger.exception("Unexpected Ollama error")
            return f"Ollama error: {e}"

    def stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        try:
            stream = self._client.chat.completions.create(
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
            logger.exception("Error in Ollama stream")
            yield f"Error: {e}"

    # ── Management ──────────────────────────────────────────────────

    def list_models(self) -> list[str]:
        """List models available in the local Ollama installation.

        Calls ``GET /api/tags`` on the Ollama host directly (not the
        OpenAI-compatible endpoint) to get the list of pulled models.
        """
        try:
            url = f"{self._raw_host}/api/tags"
            req = Request(url, method="GET")
            with urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [
                    m["name"] for m in data.get("models", [])
                ]
                return sorted(models)
        except (URLError, json.JSONDecodeError, OSError) as e:
            logger.warning("OllamaProvider: failed to list models: %s", e)
            return [self._model]

    def health_check(self) -> bool:
        """Check if Ollama is running by sending a tiny prompt.

        Sends "Hello" to the model. If it responds, Ollama is healthy.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5,
                stream=False,
            )
            return bool(response.choices[0].message.content)
        except Exception:
            return False

    def set_model(self, model_name: str) -> None:
        self._model = model_name
        logger.info("OllamaProvider: switched to model %s", model_name)

    # ── Properties ──────────────────────────────────────────────────

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def token_limit(self) -> int:
        # Conservative default — Ollama models vary greatly
        return 32_768

    @property
    def model_info(self) -> dict:
        return {
            "model": self._model,
            "provider": "ollama",
            "host": self._host,
            "token_limit": self.token_limit,
            "running": "local",
        }
