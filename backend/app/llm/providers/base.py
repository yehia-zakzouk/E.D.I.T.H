"""Abstract provider interface for LLM backends.

Every provider exposes the same methods so that EDITH never knows which
provider is actually running. Switching between Ollama, OpenAI, or any
future model requires **zero code changes** — just a settings change.

Interface
---------
- ``chat(messages, **kwargs)``          → Full text response
- ``stream(messages, **kwargs)``        → Yields tokens as they arrive
- ``list_models()``                     → Available models from this provider
- ``health_check()``                    → True if the provider is reachable
- ``set_model(model_name)``             → Hot-switch the active model
- ``model_name`` (property)             → Currently active model name
- ``provider_name`` (property)          → Provider identifier (e.g. "ollama")
- ``model_info`` (property)             → Dict with model metadata
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterator


class BaseProvider(ABC):
    """Abstract LLM provider that EDITH uses for all model interactions."""

    # ── Core API ────────────────────────────────────────────────────

    @abstractmethod
    def chat(self, messages: list[dict], **kwargs) -> str:
        """Send a message list and return the full response string.

        Args:
            messages: Standard OpenAI-format message list:
                ``[{"role": "user", "content": "..."}]``
            **kwargs: Overrides for temperature, max_tokens, etc.

        Returns:
            The assistant's response text.
        """

    @abstractmethod
    def stream(self, messages: list[dict], **kwargs) -> Iterator[str]:
        """Send a message list and yield response tokens as they arrive.

        Args:
            messages: Standard OpenAI-format message list.
            **kwargs: Overrides for temperature, max_tokens, etc.

        Yields:
            Text tokens/chunks as the model generates them.
        """

    # ── Management ──────────────────────────────────────────────────

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return a list of available model names from this provider.

        For OpenAI, this calls the Models API.
        For Ollama, this calls ``/api/tags``.
        """

    @abstractmethod
    def health_check(self) -> bool:
        """Check if the provider is reachable and responsive.

        Sends a tiny prompt and expects a response. Returns True if
        the provider responded, False otherwise.
        """

    def set_model(self, model_name: str) -> None:
        """Hot-switch the active model.

        The next call to ``chat`` or ``stream`` uses this model.
        No reconnect or restart is required.

        Default implementation stores the name. Providers with
        additional setup (e.g. context length caching) override this.
        """
        self._model = model_name

    # ── Properties ──────────────────────────────────────────────────

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable identifier for the active model."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier, e.g. ``"ollama"`` or ``"openai"``."""

    @property
    def model_info(self) -> dict:
        """Return metadata about the active model and provider.

        Override in subclasses to provide provider-specific info
        (context length, RAM usage, local/cloud, etc.)
        """
        return {
            "model": self.model_name,
            "provider": self.provider_name,
            "token_limit": getattr(self, "token_limit", None),
        }

    # ── Backward-compat helpers ─────────────────────────────────────

    def ask(self, prompt: str, **kwargs) -> str:
        """Legacy: wrap a prompt string into a message list and call ``chat``."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def ask_stream(self, prompt: str, **kwargs) -> Iterator[str]:
        """Legacy: wrap a prompt string into a message list and call ``stream``."""
        yield from self.stream([{"role": "user", "content": prompt}], **kwargs)
