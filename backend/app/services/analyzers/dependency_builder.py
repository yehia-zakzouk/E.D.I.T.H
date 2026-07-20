from pathlib import Path

from app.models.dependency import Dependency
from app.models.project import Project


class DependencyBuilder:

    def build(self, project: Project) -> Project:

        project.dependencies.clear()

        # Build a lookup table:
        # "app.services.indexer" -> "indexer.py"
        module_lookup = {}

        for file in project.indexed_files:

            relative = file.path.relative_to(project.root)

            module = ".".join(relative.with_suffix("").parts)

            module_lookup[module] = relative.as_posix()

        # Build dependencies
        for file in project.indexed_files:

            relative = file.path.relative_to(project.root)

            source = relative.as_posix()

            for imp in file.analysis.imports:

                target = None

                # Exact match
                if imp in module_lookup:
                    target = module_lookup[imp]

                else:
                    # Parent package match
                    for module in module_lookup:

                        if imp.startswith(module):

                            target = module_lookup[module]
                            break

                if target:

                    project.dependencies.append(
                        Dependency(
                            source=source,
                            target=target,
                            kind="import"
                        )
                    )

        return project