from pathlib import Path
from pydantic import BaseModel, Field

from app.models.file_index import FileIndex
from app.models.dependency import Dependency
from app.graph.repository_graph import RepositoryGraph


class Project(BaseModel):

    root: Path

    files: list[Path] = Field(default_factory=list)
    indexed_files: list[FileIndex] = Field(default_factory=list)

    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)

    dependencies: list[Dependency] = Field(default_factory=list)

    graph: RepositoryGraph = Field(default_factory=RepositoryGraph)

    build_system: str | None = None
    database: str | None = None
    testing_framework: str | None = None

    docker: bool = False
    git: bool = False