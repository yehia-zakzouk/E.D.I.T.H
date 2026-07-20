from pathlib import Path
from typing import Iterable, Optional

from app.database.repositories.file_repository import FileRepository
from app.database.repositories.metrics_repository import MetricsRepository
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.relationship_repository import RelationshipRepository
from app.database.repositories.symbol_repository import SymbolRepository
from app.database.repositories.technology_repository import TechnologyRepository
from app.models.project import Project
from app.models.file_index import FileIndex


class MemoryEngine:

    def __init__(self, connection):
        self.project_repo = ProjectRepository(connection)
        self.file_repo = FileRepository(connection)
        self.symbol_repo = SymbolRepository(connection)
        self.metrics_repo = MetricsRepository(connection)
        self.technology_repo = TechnologyRepository(connection)
        self.relationship_repo = RelationshipRepository(connection)

    def save(self, project: Project) -> Project:
        project_id = self.project_repo.save(project)
        project.id = project_id

        self.technology_repo.save_many(project_id, self._project_technologies(project))

        file_ids = self.file_repo.save_files(project_id, project.root, project.indexed_files)

        self._save_symbols(project.indexed_files)
        self._save_metrics(project.indexed_files)
        self._save_relationships(project, project_id, file_ids)

        return project

    def load(self, path: str) -> Optional[Project]:
        project = self.project_repo.load(path)

        if project is None:
            return None

        files = self.file_repo.load_by_project(project.id, project.root)
        project.indexed_files = files

        technologies = self.technology_repo.load_by_project(project.id)
        self._apply_technologies(project, technologies)

        return project

    def delete(self, path: str):
        self.project_repo.delete(path)

    def _project_technologies(self, project: Project) -> list[tuple[str, str]]:
        technologies = []

        for language in project.languages:
            technologies.append(("language", language))

        for framework in project.frameworks:
            technologies.append(("framework", framework))

        if project.build_system:
            technologies.append(("build_system", project.build_system))

        if project.database:
            technologies.append(("database", project.database))

        if project.testing_framework:
            technologies.append(("testing_framework", project.testing_framework))

        if project.docker:
            technologies.append(("tool", "Docker"))

        if project.git:
            technologies.append(("tool", "Git"))

        return technologies

    def _save_symbols(self, files: Iterable[FileIndex]):
        for file in files:
            if file.id is None:
                continue

            self.symbol_repo.delete_by_file(file.id)

            if file.analysis is None:
                continue

            symbols = []
            for name in file.analysis.classes:
                symbols.append((name, "class", None))
            for name in file.analysis.functions:
                symbols.append((name, "function", None))
            for name in file.analysis.methods:
                symbols.append((name, "method", None))

            self.symbol_repo.save_many(file.id, symbols)

    def _save_metrics(self, files: Iterable[FileIndex]):
        for file in files:
            if file.id is None or file.analysis is None:
                continue

            self.metrics_repo.save(
                file.id,
                todo_count=len(file.analysis.todos),
                function_count=len(file.analysis.functions),
                class_count=len(file.analysis.classes),
                complexity=file.analysis.complexity,
            )

    def _save_relationships(self, project: Project, project_id: int, file_ids: dict[str, int]):
        relationships = []
        for dependency in project.dependencies:
            source_id = file_ids.get(dependency.source)
            target_id = file_ids.get(dependency.target)
            if source_id is None or target_id is None:
                continue

            relationships.append((source_id, target_id, dependency.kind))

        self.relationship_repo.save_many(project_id, relationships)

    def _apply_technologies(self, project: Project, technologies: list[tuple[str, str]]):
        for category, name in technologies:
            if category == "language" and name not in project.languages:
                project.languages.append(name)
            elif category == "framework" and name not in project.frameworks:
                project.frameworks.append(name)
            elif category == "build_system":
                project.build_system = name
            elif category == "database":
                project.database = name
            elif category == "testing_framework":
                project.testing_framework = name
            elif category == "tool":
                if name == "Docker":
                    project.docker = True
                elif name == "Git":
                    project.git = True

        project.languages = sorted(project.languages)
        project.frameworks = sorted(project.frameworks)
