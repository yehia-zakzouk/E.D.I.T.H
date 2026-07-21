"""Tests for the AI provider abstraction and OpenAI provider."""

from app.ai.provider import BaseProvider, ProviderRegistry


class _MinimalProvider(BaseProvider):
    """Minimal concrete provider for testing."""

    def __init__(self):
        self._called = []

    def ask(self, prompt: str, **kwargs) -> str:
        self._called.append(("ask", prompt))
        return f"answered: {prompt[:20]}"

    def ask_stream(self, prompt: str, **kwargs):
        self._called.append(("ask_stream", prompt))
        yield "chunk1"
        yield "chunk2"

    @property
    def model_name(self) -> str:
        return "test-model"

    @property
    def token_limit(self) -> int:
        return 4096


def test_provider_abstraction():
    """BaseProvider should enforce the interface."""
    p = _MinimalProvider()
    assert p.model_name == "test-model"
    assert p.token_limit == 4096
    assert p.ask("hello") == "answered: hello"
    chunks = list(p.ask_stream("hello"))
    assert chunks == ["chunk1", "chunk2"]


def test_provider_registry():
    """Registry should store and retrieve provider classes."""
    r = ProviderRegistry()
    r.register("test", _MinimalProvider)
    assert "test" in r.list()
    assert r.get("test") is _MinimalProvider
    assert r.get("nonexistent") is None
