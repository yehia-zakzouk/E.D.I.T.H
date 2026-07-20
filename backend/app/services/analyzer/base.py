from abc import ABC, abstractmethod

from app.models.file_analysis import FileAnalysis


class BaseAnalyzer(ABC):
    """
    Base class for all language analyzers.
    """

    @abstractmethod
    def extract(self, source: str) -> FileAnalysis:
        """
        Analyze source code and return a FileAnalysis object.
        """
        pass