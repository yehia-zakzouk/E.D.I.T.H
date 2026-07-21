"""EDITH LLM Layer — clean provider abstraction for any model backend.

The goal: switching between OpenAI, Ollama, or any future model requires
**zero code changes** — just a settings change.

Architecture
------------
User → EDITH UI → Provider Factory → { Ollama | OpenAI | ... } → LLM
                                     ↓
                              Provider Interface
                                     ↓
                              Repository Context
                                     ↓
                              Response

Usage
-----
    from app.llm import ProviderFactory

    provider = ProviderFactory.create()
    answer = provider.chat([{"role": "user", "content": "Hello"}])
    for chunk in provider.stream([{"role": "user", "content": "Hi"}]):
        print(chunk)
    models = provider.list_models()
    healthy = provider.health_check()
    provider.set_model("qwen2.5-coder:14b")
"""

from app.llm.providers.base import BaseProvider
from app.llm.providers.openai_provider import OpenAIProvider
from app.llm.providers.ollama_provider import OllamaProvider
from app.llm.provider_factory import ProviderFactory
from app.llm.config import LLMConfig

__all__ = [
    "BaseProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "ProviderFactory",
    "LLMConfig",
]
