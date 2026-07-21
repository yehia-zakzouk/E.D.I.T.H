from app.core.config import config, logger
from app.models.project import Project
from app.services.analyzer.router import AnalyzerRouter
from app.services.analyzers.dependency_builder import DependencyBuilder
from app.graph.graph_builder import GraphBuilder
from app.services.memory_engine import MemoryEngine
from app.services.context_engine import ContextEngine


class KnowledgeExtractor:

    def __init__(self):
        self.router = AnalyzerRouter()
        self.dependency_builder = DependencyBuilder()
        self.graph_builder = GraphBuilder()
        self.memory_engine = MemoryEngine()
        self.context_engine = ContextEngine()

    def analyze(self, project: Project) -> Project:

        logger.info("Extracting knowledge from files")

        for file in project.indexed_files:

            analyzer = self.router.get(file.path)

            if analyzer is None:
                logger.warning("Skipping %s (no analyzer)", file.path.name)
                continue

            try:

                source = file.path.read_text(
                    encoding=config.parser.encoding,
                    errors=config.parser.errors,
                )

                analysis = analyzer.analyze(source)

                if analysis is None:
                    logger.error("%s: Analyzer returned None", file.path.name)
                    continue

                file.analysis = analysis

                logger.debug("Analyzed %s", file.path.name)

            except Exception as e:
                logger.error("%s: %s", file.path.name, e, exc_info=True)

        project.indexed_files = [
            file for file in project.indexed_files
            if file.analysis is not None
        ]

        project = self.dependency_builder.build(project)
        project = self.graph_builder.build(project)

        # Persist a lightweight snapshot to the Memory Engine for later queries
        try:
            self.memory_engine.save_project(project)
        except Exception:
            logger.exception("Failed saving project to MemoryEngine")

        # Context Engine indexing placeholder (no-op for now)
        try:
            # Keep the index call to trigger any future indexing logic
            _ = self.context_engine.build_context("", project)
        except Exception:
            logger.exception("ContextEngine build failed")

        return project
