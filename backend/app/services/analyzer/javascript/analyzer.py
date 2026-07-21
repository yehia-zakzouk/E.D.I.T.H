from app.services.analyzer.base import BaseAnalyzer
from app.models.file_analysis import FileAnalysis


class JavaScriptAnalyzer(BaseAnalyzer):

    def parse(self, source: str):
        return source

    def extract(self, parsed: str) -> FileAnalysis:
        return FileAnalysis()