"""LLM provider implementations.

Available providers
-------------------
- ``BaseProvider`` — Abstract interface (from ``base.py``)
- ``OpenAIProvider`` — Talks to OpenAI's Chat Completions API
- ``OllamaProvider`` — Talks to local Ollama via OpenAI-compatible API
"""

from app.llm.providers.base import BaseProvider
from app.llm.providers.openai_provider import OpenAIProvider
from app.llm.providers.ollama_provider import OllamaProvider

__all__ = [
    "BaseProvider",
    "OpenAIProvider",
    "OllamaProvider",
]
