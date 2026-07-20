from pathlib import Path
from app.services.analyzer.python import PythonAnalyzer


class AnalyzerRouter:
    """S
    Routes files to the correct language analyzer.
    """

    def __init__(self):

        self.analyzers = {
            ".py": PythonAnalyzer(),
        }

    def get(self, path: Path):

        return self.analyzers.get(path.suffix.lower())