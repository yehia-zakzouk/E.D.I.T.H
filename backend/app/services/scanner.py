from pathlib import Path

from app.core.constants import IGNORED_DIRECTORIES
from app.utils.file_utils import should_ignore


class RepositoryScanner:
    """
    Scans a repository and returns all project files.
    """

    def scan(self, root: str) -> list[Path]:
        repository = Path(root)

        files = []

        for path in repository.rglob("*"):

            if should_ignore(path, IGNORED_DIRECTORIES):
                continue

            if path.is_file():
                files.append(path)

        return files