from app.models.project import Project
from app.services.file_parser import FileParser


class RepositoryIndexer:

    def __init__(self):

        self.parser = FileParser()

    def index(self, project: Project) -> Project:

        project.indexed_files = []

        for file in project.files:

            project.indexed_files.append(
                self.parser.parse(file)
            )

        return project 