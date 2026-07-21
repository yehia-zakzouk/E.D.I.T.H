"""Tests for the enhanced AI Context Engine."""

from pathlib import Path

from app.ai.context_engine import ContextEngine, _extract_keywords, _split_identifier
from app.models.project import Project
from app.models.file_index import FileIndex
from app.models.file_analysis import FileAnalysis
from app.models.symbol import Symbol
from app.models.dependency import Dependency
from app.models.relationship import Relationship


def _make_project() -> Project:
    p = Project(root=Path("/repo"))

    fa1 = FileAnalysis(module_docstring="Database connection and session management")
    fa1.symbols.append(Symbol(name="DatabaseManager", qualified_name="DatabaseManager", kind="class", file="db.py", line=1, docstring="Manages database connections"))
    fa1.symbols.append(Symbol(name="connect", qualified_name="DatabaseManager.connect", kind="method", file="db.py", line=10, parent="DatabaseManager"))
    fa1.imports = ["sqlalchemy", "os"]

    fa2 = FileAnalysis(module_docstring="User authentication and authorization")
    fa2.symbols.append(Symbol(name="UserService", qualified_name="UserService", kind="class", file="auth.py", line=1, docstring="Handles user auth"))
    fa2.symbols.append(Symbol(name="login", qualified_name="UserService.login", kind="method", file="auth.py", line=15, parent="UserService"))

    fa3 = FileAnalysis(module_docstring="CLI entry point")
    fa3.symbols.append(Symbol(name="main", qualified_name="main", kind="function", file="cli.py", line=1))

    f1 = FileIndex(path=Path("/repo/db.py"), size=100, lines=30, hash="a", last_modified=0.0)
    f1.analysis = fa1
    f2 = FileIndex(path=Path("/repo/auth.py"), size=200, lines=60, hash="b", last_modified=0.0)
    f2.analysis = fa2
    f3 = FileIndex(path=Path("/repo/cli.py"), size=50, lines=15, hash="c", last_modified=0.0)
    f3.analysis = fa3

    p.indexed_files = [f1, f2, f3]
    p.dependencies = [
        Dependency(source="cli.py", target="auth.py", kind="imports"),
        Dependency(source="auth.py", target="db.py", kind="imports"),
    ]
    p.relationships = [
        Relationship(source="cli.py", target="auth.py", kind="imports"),
        Relationship(source="auth.py", target="db.py", kind="imports"),
    ]
    return p


class TestContextEngine:

    def test_build_context_keyword_match(self):
        engine = ContextEngine()
        project = _make_project()
        ctx = engine.build_context("explain DatabaseManager", project)

        assert ctx["question"] == "explain DatabaseManager"
        assert ctx["target"] == "DatabaseManager"
        assert "relevant_files" in ctx
        assert any("db.py" in r["path"] for r in ctx["relevant_files"])

    def test_build_context_no_match(self):
        engine = ContextEngine()
        project = _make_project()
        ctx = engine.build_context("Hello world", project)
        assert ctx["target"] is None
        assert "relevant_files" not in ctx or len(ctx.get("relevant_files", [])) == 0

    def test_build_context_with_relationships(self):
        engine = ContextEngine()
        project = _make_project()
        ctx = engine.build_context("explain UserService", project)
        if "relevant_relationships" in ctx:
            assert len(ctx["relevant_relationships"]) > 0

    def test_build_context_summary(self):
        engine = ContextEngine()
        project = _make_project()
        ctx = engine.build_context("where is DatabaseManager used", project)
        assert "summary" in ctx
        assert "relevant files" in ctx["summary"].lower() or "found" in ctx["summary"].lower()


class TestHelpers:

    def test_extract_keywords(self):
        keywords = _extract_keywords("explain DatabaseManager", target="DatabaseManager")
        assert "database" in keywords or "databasemanager" in keywords

    def test_extract_keywords_no_target(self):
        keywords = _extract_keywords("what is this")
        assert len(keywords) == 0 or all(len(k) <= 2 for k in keywords)

    def test_split_identifier(self):
        assert _split_identifier("DatabaseManager") == ["database", "manager"]
        assert _split_identifier("HTTPClient") == ["http", "client"]
        assert _split_identifier("parseURL") == ["parse", "url"]
