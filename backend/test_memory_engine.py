from pathlib import Path
import tempfile

from app.database.database import DatabaseManager
from app.database.memory_engine import MemoryEngine
from app.models.project import Project
from app.services.scanner import RepositoryScanner
from app.services.detector import ProjectDetector
from app.services.indexer import RepositoryIndexer
from app.services.knowledge_extractor import KnowledgeExtractor


def test_memory_engine_save_and_load():
    project_root = Path(__file__).resolve().parent

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "edith_test.db"

        db = DatabaseManager(str(db_path))
        db.initialize()

        try:
            memory = MemoryEngine(db.connection)

            project = Project(root=project_root)

            project.files = RepositoryScanner().scan(str(project.root))
            project = ProjectDetector().detect(project)
            project = RepositoryIndexer().index(project)
            project = KnowledgeExtractor().analyze(project)

            saved_project = memory.save(project)
            loaded_project = memory.load(str(project.root))

            assert loaded_project is not None
            assert loaded_project.id == saved_project.id
            assert loaded_project.root == saved_project.root
            assert loaded_project.docker == saved_project.docker
            assert loaded_project.git == saved_project.git
        finally:
            db.close()


if __name__ == "__main__":
    test_memory_engine_save_and_load()
    print("Memory engine smoke test passed.")
