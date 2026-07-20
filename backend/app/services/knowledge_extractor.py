from app.models.project import Project
from app.services.analyzer.router import AnalyzerRouter
from app.services.analyzers.dependency_builder import DependencyBuilder
from app.graph.graph_builder import GraphBuilder


class KnowledgeExtractor:

    def __init__(self):
        self.router = AnalyzerRouter()
        self.dependency_builder = DependencyBuilder()
        self.graph_builder = GraphBuilder()

    def analyze(self, project: Project) -> Project:

        print("\n🧩 Extracting knowledge from files...\n")

        for file in project.indexed_files:

            analyzer = self.router.get(file.path)

            if analyzer is None:
                print(f"⏭️  Skipping {file.path.name} (no analyzer)")
                continue

            try:

                source = file.path.read_text(
                    encoding="utf-8",
                    errors="ignore"
                )

                analysis = analyzer.extract(source)

                if analysis is None:
                    print(f"❌ {file.path.name}: Analyzer returned None")
                    continue

                file.analysis = analysis

                print(f"✅ {file.path.name}")

            except Exception as e:

                print(f"❌ {file.path.name}: {e}")

        project.indexed_files = [
            file for file in project.indexed_files
            if file.analysis is not None
        ]

        project = self.dependency_builder.build(project)
        project = self.graph_builder.build(project)
        return project
