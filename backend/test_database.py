from pathlib import Path

from app.database.database import DatabaseManager
from app.database.repositories.project_repository import ProjectRepository
from app.models.project import Project


def main():
    # Always use the same database
    project_root = Path(__file__).resolve().parent.parent
    db_path = project_root / "data" / "edith.db"

    print(f"Using database: {db_path}")

    # Initialize database
    db = DatabaseManager(str(db_path))
    db.initialize()

    # Create repository
    project_repo = ProjectRepository(db.connection)

    # Create a test project
    project = Project(
        root=project_root
    )

    # Save project
    project_id = project_repo.save(project)

    print(f"\n✅ Project saved with ID: {project_id}")

    # Load project
    loaded_project = project_repo.load(str(project.root))

    print("\nLoaded Project:")
    print(loaded_project)

    db.close()


if __name__ == "__main__":
    main()