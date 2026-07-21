"""LLM configuration — controls which provider and model EDITH uses.

Configured via environment variables (prefixed with EDITH_) or .env file:

    EDITH_LLM__PROVIDER=ollama
    EDITH_LLM__OLLAMA_HOST=http://localhost:11434/v1
    EDITH_LLM__OLLAMA_MODEL=qwen2.5-coder:14b
    EDITH_LLM__OPENAI_MODEL=gpt-4o-mini
"""

from __future__ import annotations

from typing import Optional

import pydantic

if pydantic.__version__.startswith("2"):
    from pydantic_settings import BaseSettings, SettingsConfigDict
else:
    from pydantic import BaseSettings
    SettingsConfigDict = None


class LLMConfig(BaseSettings):
    """Configuration for the LLM provider layer.

    Reads from environment variables with the ``EDITH_LLM__`` prefix.

    Environment variables
    ---------------------
    EDITH_LLM__PROVIDER
        Which provider to use: "ollama", "openai", etc.
    EDITH_LLM__OLLAMA_HOST
        Base URL for Ollama's OpenAI-compatible API.
    EDITH_LLM__OLLAMA_MODEL
        Default model name for Ollama.
    EDITH_LLM__OPENAI_API_KEY
        API key for OpenAI.
    EDITH_LLM__OPENAI_MODEL
        Default model name for OpenAI.
    """

    # ── Provider selection ──
    provider: str = "openai"

    # ── Ollama settings ──
    ollama_host: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2.5-coder:14b"

    # ── OpenAI settings ──
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    # ── Shared settings ──
    temperature: float = 0.7
    max_tokens: int = 4096

    if SettingsConfigDict is not None:
        model_config = SettingsConfigDict(
            env_prefix="EDITH_LLM__",
            case_sensitive=False,
            env_nested_delimiter="__",
        )
    else:
        class Config:
            env_prefix = "EDITH_LLM__"
            case_sensitive = False


# Singleton
llm_config = LLMConfig()
