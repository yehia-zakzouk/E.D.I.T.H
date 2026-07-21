from pathlib import Path
from typing import Iterable, Optional

import json
from app.database.repositories.call_repository import CallRepository
from app.database.repositories.file_repository import FileRepository
from app.database.repositories.inheritance_repository import InheritanceRepository
from app.database.repositories.metrics_repository import MetricsRepository
from app.database.repositories.project_repository import ProjectRepository
from app.database.repositories.relationship_repository import RelationshipRepository
from app.database.repositories.symbol_repository import SymbolRepository
from app.database.repositories.technology_repository import TechnologyRepository
from app.models.project import Project
from app.models.file_index import FileIndex
from app.models.file_analysis import FileAnalysis
from app.models.relationship import Relationship
from app.models.dependency import Dependency
from app.models.symbol import Symbol, Parameter, CallRelation, InheritanceRelation


class MemoryEngine:

    def __init__(self, connection):
        self.project_repo = ProjectRepository(connection)
        self.file_repo = FileRepository(connection)
        self.symbol_repo = SymbolRepository(connection)
        self.call_repo = CallRepository(connection)
        self.inheritance_repo = InheritanceRepository(connection)
        self.metrics_repo = MetricsRepository(connection)
        self.technology_repo = TechnologyRepository(connection)
        self.relationship_repo = RelationshipRepository(connection)

    def save(self, project: Project) -> Project:
        try:
            self.project_repo.begin_transaction()

            project_id = self.project_repo.save(project)
            project.id = project_id

            self.technology_repo.save_many(project_id, self._project_technologies(project))

            file_ids = self.file_repo.save_files(project_id, project.root, project.indexed_files)

            self._save_symbols(project.indexed_files)
            self._save_calls(project.indexed_files)
            self._save_inheritance_relations(project.indexed_files)
            self._save_metrics(project.indexed_files)
            self._save_relationships(project, project_id, file_ids)

            self.project_repo.commit()

            return project
        except Exception:
            self.project_repo.rollback_transaction()
            raise

    def load(self, path: str) -> Optional[Project]:
        project = self.project_repo.load(path)

        if project is None:
            return None

        files = self.file_repo.load_by_project(project.id, project.root)
        project.indexed_files = files

        technologies = self.technology_repo.load_by_project(project.id)
        self._apply_technologies(project, technologies)

        self._load_file_metrics(project.indexed_files)
        self._load_file_symbols(project.indexed_files)
        self._load_file_calls(project.indexed_files)
        self._load_file_inheritance_relations(project.indexed_files)

        project.relationships = self._load_relationships(project.id, files, project.root)
        project.dependencies = self._build_dependencies_from_relationships(project)

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

            file_path = file.path.as_posix()
            symbols = []
            for symbol in file.analysis.symbols:
                symbols.append(
                    (
                        symbol.qualified_name,
                        symbol.kind,
                        symbol.file or file_path,
                        symbol.parent,
                        symbol.line,
                        symbol.end_line,
                        symbol.column,
                        symbol.return_type,
                        symbol.decorators,
                        symbol.type_hints,
                        [
                            {
                                "name": param.name,
                                "annotation": param.annotation,
                                "default": param.default,
                                "kind": param.kind,
                            }
                            for param in symbol.parameters
                        ],
                        symbol.docstring,
                    )
                )

            self.symbol_repo.save_many(file.id, symbols)

    def _save_calls(self, files: Iterable[FileIndex]):
        for file in files:
            if file.id is None:
                continue

            self.call_repo.delete_by_file(file.id)

            if file.analysis is None:
                continue

            calls = [
                (call.caller, call.callee, call.line)
                for call in file.analysis.calls
            ]
            if calls:
                self.call_repo.save_many(file.id, calls)

    def _save_inheritance_relations(self, files: Iterable[FileIndex]):
        for file in files:
            if file.id is None:
                continue

            self.inheritance_repo.delete_by_file(file.id)

            if file.analysis is None:
                continue

            inheritance_relations = [
                (inheritance.child, inheritance.parent, inheritance.line)
                for inheritance in file.analysis.inheritance_relations
            ]
            if inheritance_relations:
                self.inheritance_repo.save_many(file.id, inheritance_relations)

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

        source_relationships = project.relationships if project.relationships else [
            Relationship(source=dependency.source, target=dependency.target, kind=dependency.kind)
            for dependency in project.dependencies
        ]

        for relationship in source_relationships:
            source_id = file_ids.get(relationship.source)
            target_id = file_ids.get(relationship.target)
            if source_id is None or target_id is None:
                continue

            relationships.append((source_id, target_id, relationship.kind))

        self.relationship_repo.save_many(project_id, relationships)

    def _load_relationships(self, project_id: int, files: list[FileIndex], project_root: Path) -> list[Relationship]:
        file_map = {
            file.id: file.path.relative_to(project_root).as_posix()
            for file in files
            if file.id is not None
        }
        raw_relationships = self.relationship_repo.load_by_project(project_id)
        relationships = []

        for source_id, target_id, kind in raw_relationships:
            source_path = file_map.get(source_id)
            target_path = file_map.get(target_id)
            if source_path is None or target_path is None:
                continue

            relationships.append(Relationship(source=source_path, target=target_path, kind=kind))

        return relationships

    def _build_dependencies_from_relationships(self, project: Project) -> list[Dependency]:
        dependencies = []
        for relationship in project.relationships:
            dependencies.append(
                Dependency(
                    source=relationship.source,
                    target=relationship.target,
                    kind=relationship.kind,
                )
            )
        return dependencies

    def _load_file_metrics(self, files: list[FileIndex]):
        for file in files:
            if file.id is None:
                continue

            metrics = self.metrics_repo.load_by_file(file.id)
            file.metrics = metrics

    def _load_file_symbols(self, files: list[FileIndex]):
        for file in files:
            if file.id is None:
                continue

            if file.analysis is not None and file.analysis.symbols:
                continue

            symbols = self.symbol_repo.load_by_file(file.id)
            if not symbols:
                continue

            if file.analysis is None:
                file.analysis = FileAnalysis()

            for name, kind, file_path, parent, line, end_line, column, return_type, decorators, type_hints, parameters, docstring in symbols:
                if kind == "class" and name not in file.analysis.classes:
                    file.analysis.classes.append(name)
                elif kind == "function" and name not in file.analysis.functions:
                    file.analysis.functions.append(name)
                elif kind == "method" and name not in file.analysis.methods:
                    file.analysis.methods.append(name)

                file.analysis.symbols.append(
                    Symbol(
                        name=name.split(".")[-1],
                        qualified_name=name,
                        kind=kind,
                        file=file_path,
                        parent=parent,
                        line=line or 0,
                        end_line=end_line,
                        column=column,
                        return_type=return_type,
                        decorators=decorators,
                        type_hints=type_hints,
                        parameters=[Parameter(**param) for param in parameters],
                        docstring=docstring,
                    )
                )

    def _load_file_calls(self, files: list[FileIndex]):
        for file in files:
            if file.id is None:
                continue

            if file.analysis is not None and file.analysis.calls:
                continue

            calls = self.call_repo.load_by_file(file.id)
            if not calls:
                continue

            if file.analysis is None:
                file.analysis = FileAnalysis()

            for caller, callee, line in calls:
                file.analysis.calls.append(
                    CallRelation(caller=caller, callee=callee, line=line)
                )

    def _load_file_inheritance_relations(self, files: list[FileIndex]):
        for file in files:
            if file.id is None:
                continue

            if file.analysis is not None and file.analysis.inheritance_relations:
                continue

            inheritance_relations = self.inheritance_repo.load_by_file(file.id)
            if not inheritance_relations:
                continue

            if file.analysis is None:
                file.analysis = FileAnalysis()

            for child, parent, line in inheritance_relations:
                file.analysis.inheritance_relations.append(
                    InheritanceRelation(child=child, parent=parent, line=line)
                )

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
