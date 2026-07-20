from app.services.analyzer.base import BaseAnalyzer
from app.models.file_analysis import FileAnalysis


class JavaScriptAnalyzer(BaseAnalyzer):

    def extract(self, source: str) -> FileAnalysis:
        return FileAnalysis()