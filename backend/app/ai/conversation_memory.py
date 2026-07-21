"""Lightweight conversation memory that preserves context across turns.

When the user asks "what about connect()?" EDITH remembers that
"DatabaseManager" was the topic of the previous question.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Turn:
    question: str
    answer: str
    intent: str = "general_question"
    entities: list[str] = field(default_factory=list)


class ConversationMemory:
    """Stores conversation turns and infers implicit context for follow-ups."""

    def __init__(self, max_turns: int = 10):
        self._turns: list[Turn] = []
        self._max_turns = max_turns

    def add_turn(
        self,
        question: str,
        answer: str,
        intent: str = "general_question",
        entities: Optional[list[str]] = None,
    ) -> None:
        self._turns.append(
            Turn(
                question=question,
                answer=answer,
                intent=intent,
                entities=entities or [],
            )
        )
        if len(self._turns) > self._max_turns:
            self._turns.pop(0)

    @property
    def last_turn(self) -> Optional[Turn]:
        return self._turns[-1] if self._turns else None

    @property
    def recent_entities(self) -> list[str]:
        """Return entities mentioned in the last few turns."""
        entities: list[str] = []
        for turn in self._turns[-3:]:
            entities.extend(turn.entities)
        return entities

    @property
    def history(self) -> list[Turn]:
        return list(self._turns)

    def build_context_summary(self) -> str:
        """Return a short natural-language summary of what was discussed.

        This is injected into prompts so the LLM knows the conversation.
        """
        if not self._turns:
            return ""

        parts = []
        for i, turn in enumerate(self._turns, 1):
            parts.append(f"{i}. User: {turn.question}")
        return "Previous conversation:\n" + "\n".join(parts)

    def clear(self) -> None:
        self._turns.clear()
