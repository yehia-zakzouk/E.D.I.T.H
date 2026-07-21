"""Tests for the Prompt Builder."""

from pathlib import Path

from app.ai.prompt_builder import PromptBuilder
from app.models.project import Project


def _sample_context() -> dict:
    return {
        "question": "explain DatabaseManager",
        "intent": "explain_class",
        "target": "DatabaseManager",
        "relevant_files": [
            {
                "path": "/repo/db.py",
                "score": 15,
                "symbols": [
                    {"name": "DatabaseManager", "kind": "class", "parent": None},
                    {"name": "DatabaseManager.connect", "kind": "method", "parent": "DatabaseManager"},
                ],
            },
            {
                "path": "/repo/auth.py",
                "score": 3,
                "symbols": [{"name": "UserService", "kind": "class", "parent": None}],
            },
        ],
        "relevant_symbols": ["DatabaseManager", "DatabaseManager.connect"],
        "relevant_relationships": [
            {"source": "auth.py", "target": "db.py", "kind": "imports"},
        ],
        "source_snippets": [
            {
                "path": "/repo/db.py",
                "preview": "class DatabaseManager:\n    def connect(self):\n        pass",
                "total_lines": 30,
            },
        ],
        "summary": "Found 2 relevant files, 2 symbols, 1 relationship",
    }


def _sample_project() -> Project:
    return Project(
        root=Path("/repo"),
        languages=["Python"],
        frameworks=["FastAPI"],
        build_system="pip",
    )


class TestPromptBuilder:

    def test_build_includes_question(self):
        builder = PromptBuilder()
        ctx = _sample_context()
        prompt = builder.build("explain DatabaseManager", ctx, _sample_project())
        assert "## Question" in prompt
        assert "explain DatabaseManager" in prompt

    def test_build_includes_system_prompt(self):
        system = "You are a test assistant."
        builder = PromptBuilder(system_prompt=system)
        assert builder.build_system_message() == system

    def test_build_repo_summary(self):
        builder = PromptBuilder()
        ctx = _sample_context()
        prompt = builder.build("hello", ctx, _sample_project())
        assert "Repository Summary" in prompt
        assert "Python" in prompt
        assert "FastAPI" in prompt

    def test_build_files_section(self):
        builder = PromptBuilder()
        ctx = _sample_context()
        prompt = builder.build("hello", ctx, _sample_project())
        assert "Relevant Files" in prompt
        assert "db.py" in prompt
        assert "DatabaseManager" in prompt

    def test_build_snippets_section(self):
        builder = PromptBuilder()
        ctx = _sample_context()
        prompt = builder.build("hello", ctx, _sample_project())
        assert "Source Code" in prompt
        assert "class DatabaseManager" in prompt

    def test_build_empty_context(self):
        builder = PromptBuilder()
        ctx = {"question": "hello"}
        prompt = builder.build("hello", ctx)
        assert "## Question" in prompt
        assert "hello" in prompt

    def test_build_relationships_section(self):
        builder = PromptBuilder()
        ctx = _sample_context()
        prompt = builder.build("hello", ctx, _sample_project())
        assert "File Relationships" in prompt or "Dependencies" in prompt
