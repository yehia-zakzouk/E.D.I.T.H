from pathlib import Path

from app.core.detection_rules import FRAMEWORK_FILES, LANGUAGE_FILES
from app.models.project import Project


class ProjectDetector:
    """
    Detects technologies used in a repository.
    """

    def detect(self, project: Project) -> Project:

        languages = set()
        frameworks = set()

        for file in project.files:

            suffix = file.suffix.lower()

            if suffix in LANGUAGE_FILES:
                languages.add(LANGUAGE_FILES[suffix])

            name = file.name

            if name in FRAMEWORK_FILES:

                framework, language = FRAMEWORK_FILES[name]

                frameworks.add(framework)

                if language:
                    languages.add(language)

                if framework == "Docker":
                    project.docker = True

                if framework == "Maven":
                    project.build_system = "Maven"

                if framework == "Gradle":
                    project.build_system = "Gradle"

        project.languages = sorted(languages)
        project.frameworks = sorted(frameworks)

        project.git = any(f.name == ".gitignore" for f in project.files)

        return project