"""Abstract provider interface for LLM backends.

Every provider must implement `ask` (and optionally `ask_stream`).
EDITH never calls an LLM SDK directly — it always goes through a provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator, Optional


class BaseProvider(ABC):
    """Abstract LLM provider that EDITH uses for all model interactions."""

    @abstractmethod
    def ask(self, prompt: str, **kwargs) -> str:
        """Send a prompt and return the full response string."""
        ...

    @abstractmethod
    def ask_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        """Send a prompt and yield response chunks as they arrive."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable identifier for the active model (e.g. 'gpt-4o-mini')."""
        ...

    @property
    @abstractmethod
    def token_limit(self) -> int:
        """Maximum number of input tokens this model supports."""
        ...


class ProviderRegistry:
    """Holds registered provider constructors so EDITH can swap backends."""

    def __init__(self):
        self._providers: dict[str, type[BaseProvider]] = {}

    def register(self, name: str, provider_cls: type[BaseProvider]) -> None:
        self._providers[name] = provider_cls

    def get(self, name: str) -> Optional[type[BaseProvider]]:
        return self._providers.get(name)

    def list(self) -> list[str]:
        return list(self._providers.keys())


# Global registry instance
registry = ProviderRegistry()
