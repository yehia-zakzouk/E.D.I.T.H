from pathlib import Path
from typing import Optional

from app.database.repositories.base_repository import BaseRepository
from app.models.project import Project


class ProjectRepository(BaseRepository):

    def save(self, project: Project) -> int:
        if self.exists(str(project.root)):
            return self.update(project)

        return self.insert(project)

    def exists(self, path: str) -> bool:
        cursor = self.connection.cursor()

        print("Checking path:", repr(path))

        cursor.execute(
            """
            SELECT 1
            FROM projects
            WHERE path = ?
            """,
            (path,),
        )

        result = cursor.fetchone()

        print("Result:", result)

        return result is not None

    def insert(self, project: Project) -> int:
        cursor = self.connection.cursor()

        print("Inserting:", repr(str(project.root)))

        cursor.execute(
            """
            INSERT INTO projects (
                name,
                path,
                docker,
                git,
                last_scan
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                project.root.name,
                str(project.root),
                int(project.docker),
                int(project.git),
            ),
        )

        return cursor.lastrowid

    def update(self, project: Project) -> int:
        cursor = self.connection.cursor()

        cursor.execute(
            """
            UPDATE projects
            SET last_scan = CURRENT_TIMESTAMP,
                docker = ?,
                git = ?
            WHERE path = ?
            """,
            (
                int(project.docker),
                int(project.git),
                str(project.root),
            ),
        )

        cursor.execute(
            """
            SELECT id
            FROM projects
            WHERE path = ?
            """,
            (str(project.root),),
        )

        row = cursor.fetchone()

        return row["id"]

    def load(self, path: str) -> Optional[Project]:
        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                name,
                path,
                created_at,
                last_scan,
                docker,
                git
            FROM projects
            WHERE path = ?
            """,
            (path,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return Project(
            id=row["id"],
            root=Path(row["path"]),
            docker=bool(row["docker"]),
            git=bool(row["git"])
        )

    def delete(self, path: str):
        cursor = self.connection.cursor()

        cursor.execute(
            """
            DELETE FROM projects
            WHERE path = ?
            """,
            (path,),
        )