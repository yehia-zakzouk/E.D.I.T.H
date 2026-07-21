"""Tests for conversation memory."""

from app.ai.conversation_memory import ConversationMemory


def test_empty_memory():
    mem = ConversationMemory()
    assert mem.last_turn is None
    assert mem.build_context_summary() == ""


def test_add_turn():
    mem = ConversationMemory()
    mem.add_turn("explain DatabaseManager", "DatabaseManager is...", intent="explain_class", entities=["DatabaseManager"])
    assert mem.last_turn is not None
    assert mem.last_turn.question == "explain DatabaseManager"
    assert mem.last_turn.answer == "DatabaseManager is..."
    assert mem.recent_entities == ["DatabaseManager"]


def test_context_summary():
    mem = ConversationMemory()
    mem.add_turn("Explain DatabaseManager", "It manages...", entities=["DatabaseManager"])
    mem.add_turn("What about connect()?", "It connects to...", entities=["connect"])
    summary = mem.build_context_summary()
    assert "Explain DatabaseManager" in summary
    assert "What about connect()?" in summary


def test_max_turns():
    mem = ConversationMemory(max_turns=2)
    mem.add_turn("Q1", "A1")
    mem.add_turn("Q2", "A2")
    mem.add_turn("Q3", "A3")
    assert len(mem.history) == 2
    assert mem.history[0].question == "Q2"
    assert mem.history[1].question == "Q3"


def test_clear():
    mem = ConversationMemory()
    mem.add_turn("Q1", "A1")
    mem.clear()
    assert mem.last_turn is None
    assert len(mem.history) == 0
