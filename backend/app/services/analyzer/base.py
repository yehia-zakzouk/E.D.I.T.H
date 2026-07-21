from abc import ABC, abstractmethod
from typing import Any

from app.models.file_analysis import FileAnalysis


class BaseAnalyzer(ABC):
    """
    Base class for all language analyzers.
    """

    @abstractmethod
    def parse(self, source: str) -> Any:
        """
        Parse raw source text into a language-specific intermediate form.
        """
        pass

    @abstractmethod
    def extract(self, parsed: Any) -> FileAnalysis:
        """
        Analyze parsed source and return a FileAnalysis object.
        """
        pass

    def analyze(self, source: str) -> FileAnalysis:
        """
        Perform full analysis from raw source text.
        """
        parsed = self.parse(source)
        return self.extract(parsed)