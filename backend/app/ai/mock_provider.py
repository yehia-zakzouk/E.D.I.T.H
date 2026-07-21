"""Mock provider for development and testing.

Returns canned responses so you can exercise the EDITH pipeline
without an API key or internet connection.
"""

from __future__ import annotations

from app.ai.provider import BaseProvider, registry


class MockProvider(BaseProvider):
    """Fake provider that returns canned responses — useful for testing."""

    model_name = "mock"
    token_limit = 4096

    def ask(self, prompt: str, **kwargs) -> str:
        lines = prompt.split("\n")
        question_line = ""
        for line in lines:
            if line.startswith("## Question"):
                question_line = line
        question = question_line.replace("## Question", "").strip()
        return (
            f"**EDITH Mock Response**\n\n"
            f"I analyzed your question: _{question}_\n\n"
            f"Here's what I found in the repository:\n\n"
            f"- The relevant files and symbols have been identified\n"
            f"- The knowledge graph shows the relationships\n"
            f"- Full context was prepared for the LLM\n\n"
            f"---\n"
            f"_To get real AI answers, set your OPENAI_API_KEY or "
            f"EDITH_AI__API_KEY environment variable._\n"
        )

    def ask_stream(self, prompt: str, **kwargs):
        yield from self.ask(prompt).split(" ")


registry.register("mock", MockProvider)
