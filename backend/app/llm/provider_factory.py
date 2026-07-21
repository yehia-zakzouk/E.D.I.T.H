"""Provider Factory — the single point of instantiation for LLM providers.

Never instantiate providers manually. Always use the factory:

    from app.llm import ProviderFactory

    provider = ProviderFactory.create()

The factory checks ``EDITH_LLM__PROVIDER`` and returns the correct
implementation. Switching providers requires changing one environment
variable — no code changes needed.
"""

from __future__ import annotations

from typing import Optional

from app.core.config import logger
from app.llm.config import llm_config
from app.llm.providers.base import BaseProvider


class ProviderFactory:
    """Creates and caches LLM provider instances.

    Usage::

        # Default (reads LLM_PROVIDER from config)
        provider = ProviderFactory.create()

        # Explicit provider name
        provider = ProviderFactory.create("ollama")

    Once created, the provider instance is cached so subsequent calls
    return the same object (singleton per provider name).
    """

    _instances: dict[str, BaseProvider] = {}

    @classmethod
    def create(cls, provider_name: Optional[str] = None) -> BaseProvider:
        """Create (or return cached) provider instance.

        Args:
            provider_name: Provider identifier — ``"ollama"``, ``"openai"``, etc.
                           If None, reads from ``EDITH_LLM__PROVIDER`` config.

        Returns:
            A configured BaseProvider instance.
        """
        name = provider_name or llm_config.provider or "openai"
        name = name.lower().strip()

        # Return cached instance if available
        if name in cls._instances:
            return cls._instances[name]

        logger.info("ProviderFactory: creating provider '%s'", name)

        provider = cls._build(name)
        cls._instances[name] = provider
        return provider

    @classmethod
    def rebuild(cls, provider_name: Optional[str] = None) -> BaseProvider:
        """Force-create a new provider instance, replacing any cached one.

        Useful after configuration changes (e.g. switching models or hosts).
        """
        name = provider_name or llm_config.provider or "openai"
        name = name.lower().strip()

        if name in cls._instances:
            del cls._instances[name]

        return cls.create(name)

    @classmethod
    def get_cached(cls, provider_name: Optional[str] = None) -> Optional[BaseProvider]:
        """Return the cached provider instance without creating one."""
        name = provider_name or llm_config.provider or "openai"
        return cls._instances.get(name.lower().strip())

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached provider instances."""
        cls._instances.clear()

    # ── Internal ────────────────────────────────────────────────────

    @classmethod
    def _build(cls, name: str) -> BaseProvider:
        """Instantiate the correct provider class based on name."""
        if name == "ollama":
            from app.llm.providers.ollama_provider import OllamaProvider
            return OllamaProvider()

        if name == "openai":
            from app.llm.providers.openai_provider import OpenAIProvider
            return OpenAIProvider()

        # Fallback to mock
        logger.warning(
            "ProviderFactory: unknown provider '%s' — falling back to mock",
            name,
        )
        from app.llm.providers.base import BaseProvider as BP

        class MockProvider(BP):
            provider_name = "mock"
            model_name = "mock"
            token_limit = 4096
            def chat(self, messages, **kwargs):
                return f"Mock response to: {messages[-1]['content'][:60]}..."
            def stream(self, messages, **kwargs):
                yield from self.chat(messages).split(" ")
            def list_models(self):
                return ["mock"]
            def health_check(self):
                return True

        return MockProvider()
