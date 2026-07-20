from pathlib import Path
import tempfile

from app.database.database import DatabaseManager
from app.database.memory_engine import MemoryEngine

from app.models.project import Project

from app.services.scanner import RepositoryScanner
from app.services.detector import ProjectDetector
from app.services.indexer import RepositoryIndexer
from app.services.repository_analyzer import RepositoryAnalyzer


def test_edith_pipeline():
    print("=" * 70)
    print("E.D.I.T.H FULL PIPELINE TEST")
    print("=" * 70)

    project_root = Path(__file__).resolve().parent

    with tempfile.TemporaryDirectory() as temp_dir:

        db_path = Path(temp_dir) / "edith.db"

        db = DatabaseManager(str(db_path))
        db.initialize()

        try:

            memory = MemoryEngine(db.connection)

            # --------------------------------------------------
            # Scan
            # --------------------------------------------------

            print("\n[1] Scanning repository...")

            project = Project(root=project_root)
            project.files = RepositoryScanner().scan(str(project.root))

            assert len(project.files) > 0

            print(f"✓ Found {len(project.files)} files")

            # --------------------------------------------------
            # Detect
            # --------------------------------------------------

            print("\n[2] Detecting technologies...")

            project = ProjectDetector().detect(project)

            print(f"Languages: {project.languages}")
            print(f"Frameworks: {project.frameworks}")
            print(f"Database: {project.database}")
            print(f"Build System: {project.build_system}")

            # --------------------------------------------------
            # Index
            # --------------------------------------------------

            print("\n[3] Indexing files...")

            project = RepositoryIndexer().index(project)

            assert len(project.indexed_files) > 0

            print(f"✓ Indexed {len(project.indexed_files)} files")

            # --------------------------------------------------
            # Analyze
            # --------------------------------------------------

            print("\n[4] Analyzing repository...")

            project = RepositoryAnalyzer().analyze(project)

            print(f"Dependencies : {len(project.dependencies)}")
            print(f"Relationships: {len(project.relationships)}")

            total_classes = 0
            total_functions = 0
            total_methods = 0

            for indexed in project.indexed_files:

                analysis = indexed.analysis

                if analysis is None:
                    continue

                total_classes += len(analysis.classes)
                total_functions += len(analysis.functions)
                total_methods += len(analysis.methods)

            print(f"Classes   : {total_classes}")
            print(f"Functions : {total_functions}")
            print(f"Methods   : {total_methods}")

            # --------------------------------------------------
            # Save
            # --------------------------------------------------

            print("\n[5] Saving project...")

            saved_project = memory.save(project)

            assert saved_project is not None

            print("✓ Saved successfully")

            # --------------------------------------------------
            # Load
            # --------------------------------------------------

            print("\n[6] Loading project...")

            loaded = memory.load(str(project.root))

            assert loaded is not None

            print("✓ Loaded successfully")

            # --------------------------------------------------
            # Validate
            # --------------------------------------------------

            print("\n[7] Validating data integrity...")

            assert loaded.root == project.root

            assert loaded.languages == project.languages
            assert loaded.frameworks == project.frameworks

            assert loaded.database == project.database
            assert loaded.build_system == project.build_system
            assert loaded.testing_framework == project.testing_framework

            assert loaded.docker == project.docker
            assert loaded.git == project.git

            assert len(loaded.indexed_files) == len(project.indexed_files)

            assert len(loaded.dependencies) == len(project.dependencies)

            assert len(loaded.relationships) == len(project.relationships)

            print("✓ Metadata OK")
            print("✓ Files OK")
            print("✓ Technologies OK")
            print("✓ Dependencies OK")
            print("✓ Relationships OK")

            print("\n" + "=" * 70)
            print("ALL TESTS PASSED")
            print("=" * 70)

        finally:
            db.close()


if __name__ == "__main__":
    test_edith_pipeline()