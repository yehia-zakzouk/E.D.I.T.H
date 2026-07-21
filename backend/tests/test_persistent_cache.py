"""Tests for the persistent project cache (database/MemoryEngine integration).

Verifies that projects can be saved to and loaded from SQLite,
and that the cache hierarchy in main.py works correctly.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.database.database import DatabaseManager
from app.database.memory_engine import MemoryEngine
from app.models.project import Project
from app.models.file_index import FileIndex
from app.models.file_analysis import FileAnalysis
from app.models.symbol import Symbol
from app.models.dependency import Dependency
from app.models.relationship import Relationship
from app.graph.repository_graph import RepositoryGraph
from app.graph.nodes import GraphNode, NodeType
from app.graph.edges import GraphEdge, EdgeType


def _create_sample_project() -> Project:
    """Build a small project with one file, one symbol, and a graph."""
    p = Project(root=Path("/test/repo"))
    p.languages = ["Python"]
    p.frameworks = ["FastAPI"]
    p.docker = True
    p.git = True

    fa = FileAnalysis(module_docstring="Sample module")
    fa.symbols.append(Symbol(
        name="DatabaseManager",
        qualified_name="DatabaseManager",
        kind="class",
        file="db.py",
        line=1,
        docstring="Manages database connections",
    ))
    fa.classes = ["DatabaseManager"]

    f = FileIndex(
        path=Path("/test/repo/db.py"),
        size=100,
        lines=30,
        hash="abc123",
        last_modified=1000.0,
    )
    f.analysis = fa

    p.indexed_files = [f]
    p.dependencies = [
        Dependency(source="main.py", target="db.py", kind="imports"),
    ]
    p.relationships = [
        Relationship(source="main.py", target="db.py", kind="imports"),
    ]

    # Add a minimal graph
    p.graph = RepositoryGraph(
        nodes=[
            GraphNode(id="/test/repo/db.py", type=NodeType.FILE, name="db.py"),
            GraphNode(id="/test/repo/db.py:DatabaseManager", type=NodeType.CLASS, name="DatabaseManager"),
        ],
        edges=[
            GraphEdge(source="/test/repo/db.py", target="/test/repo/db.py:DatabaseManager", relation=EdgeType.CONTAINS),
        ],
    )
    return p


class TestMemoryEnginePersistence:

    def test_save_and_load_project(self):
        """Save a project to SQLite, then load it back and verify integrity."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = DatabaseManager(str(db_path))
            db.initialize()

            try:
                mem = MemoryEngine(db.connection)
                project = _create_sample_project()

                # Save
                saved = mem.save(project)
                assert saved.id is not None
                assert saved.id > 0

                # Load
                loaded = mem.load(str(project.root))
                assert loaded is not None
                assert loaded.root == project.root
                assert loaded.languages == project.languages
                assert loaded.frameworks == project.frameworks
                assert loaded.docker == project.docker
                assert loaded.git == project.git
                assert len(loaded.indexed_files) == 1

                # Verify symbol data survived the round-trip
                f = loaded.indexed_files[0]
                assert f.analysis is not None
                assert len(f.analysis.symbols) >= 1
                sym = f.analysis.symbols[0]
                assert sym.name == "DatabaseManager"
                assert sym.kind == "class"
                assert sym.docstring == "Manages database connections"

                # Graph nodes are rebuilt in main.py's scan_repository
                # (MemoryEngine itself does not restore the graph)

            finally:
                db.close()

    def test_overwrite_existing_project(self):
        """Saving the same project path again should update, not duplicate."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = DatabaseManager(str(db_path))
            db.initialize()
            try:
                mem = MemoryEngine(db.connection)
                project = _create_sample_project()

                saved1 = mem.save(project)
                id1 = saved1.id

                # Modify and save again
                project.languages = ["Python", "JavaScript"]
                saved2 = mem.save(project)
                id2 = saved2.id

                # Same project (update, not insert) — same ID
                assert id2 == id1, "Re-saving should update, not insert a new row"

                # Load back and verify updated data
                loaded = mem.load(str(project.root))
                assert loaded is not None
                assert "JavaScript" in loaded.languages
                assert len(loaded.languages) == 2

            finally:
                db.close()

    def test_save_multiple_files(self):
        """Multiple indexed files should all be persisted and restored."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = DatabaseManager(str(db_path))
            db.initialize()
            try:
                mem = MemoryEngine(db.connection)
                project = _create_sample_project()

                # Add a second file
                fa2 = FileAnalysis(module_docstring="CLI tools")
                fa2.symbols.append(Symbol(
                    name="main",
                    qualified_name="main",
                    kind="function",
                    file="cli.py",
                    line=1,
                ))
                fa2.functions = ["main"]

                f2 = FileIndex(
                    path=Path("/test/repo/cli.py"),
                    size=50,
                    lines=15,
                    hash="def456",
                    last_modified=1001.0,
                )
                f2.analysis = fa2
                project.indexed_files.append(f2)

                saved = mem.save(project)
                assert saved.id is not None

                loaded = mem.load(str(project.root))
                assert loaded is not None
                assert len(loaded.indexed_files) == 2

                # Find the cli file
                cli_file = next((f for f in loaded.indexed_files if "cli.py" in str(f.path)), None)
                assert cli_file is not None
                assert cli_file.analysis is not None
                assert "main" in cli_file.analysis.functions

            finally:
                db.close()

    def test_load_nonexistent_project(self):
        """Loading a path that was never saved should return None."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = DatabaseManager(str(db_path))
            db.initialize()
            try:
                mem = MemoryEngine(db.connection)
                result = mem.load("/nonexistent/path")
                assert result is None
            finally:
                db.close()

    def test_project_exists_check(self):
        """The exists method should correctly detect saved projects."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = DatabaseManager(str(db_path))
            db.initialize()
            try:
                mem = MemoryEngine(db.connection)
                assert mem.project_repo.exists("/nonexistent") is False

                project = _create_sample_project()
                mem.save(project)
                assert mem.project_repo.exists(str(project.root)) is True
            finally:
                db.close()

    def test_delete_project(self):
        """Deleting a project should remove it and return None on subsequent load."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            db = DatabaseManager(str(db_path))
            db.initialize()
            try:
                mem = MemoryEngine(db.connection)
                project = _create_sample_project()
                mem.save(project)

                # Load to confirm it exists
                loaded = mem.load(str(project.root))
                assert loaded is not None

                # Delete
                mem.delete(str(project.root))
                result = mem.load(str(project.root))
                assert result is None
            finally:
                db.close()
