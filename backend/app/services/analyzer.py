from app.models.project import Project
from app.services.analyzers.symbol_extractor import SymbolExtractor


class RepositoryAnalyzer:

    def analyze(self, project: Project) -> Project:

        for file in project.indexed_files:

            try:
                source = file.path.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

                extractor = SymbolExtractor()
                file.analysis = extractor.extract(source)

            except Exception as e:
                print(f"❌ Failed to analyze {file.path.name}: {e}")

        return project