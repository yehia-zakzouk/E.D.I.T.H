from dataclasses import asdict
from pathlib import Path
import json
import sqlite3

from app.database.repositories.base_repository import BaseRepository
from app.models.file_analysis import FileAnalysis
from app.models.file_index import FileIndex


class FileRepository(BaseRepository):

    def save_files(self, project_id: int, project_root: Path, files: list[FileIndex]) -> dict[str, int]:
        file_ids = {}

        for file in files:
            relative_path = file.path.relative_to(project_root).as_posix()
            file_id = self.save(project_id, relative_path, file)
            file.id = file_id
            file_ids[relative_path] = file_id

        return file_ids

    def save(self, project_id: int, relative_path: str, file: FileIndex) -> int:
        if self.exists(project_id, relative_path):
            return self.update(project_id, relative_path, file)

        return self.insert(project_id, relative_path, file)

    def exists(self, project_id: int, relative_path: str) -> bool:
        cursor = self.get_cursor()

        cursor.execute(
            """
            SELECT 1
            FROM files
            WHERE project_id = ?
              AND path = ?
            """,
            (project_id, relative_path),
        )

        return cursor.fetchone() is not None

    def insert(self, project_id: int, relative_path: str, file: FileIndex) -> int:
        cursor = self.get_cursor()

        cursor.execute(
            """
            INSERT INTO files (
                project_id,
                path,
                hash,
                language,
                size,
                lines,
                last_modified,
                analysis_data
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                relative_path,
                file.hash,
                getattr(file, "language", None),
                file.size,
                file.lines,
                file.last_modified,
                json.dumps(asdict(file.analysis), default=str) if file.analysis is not None else None,
            ),
        )

        return cursor.lastrowid

    def update(self, project_id: int, relative_path: str, file: FileIndex) -> int:
        cursor = self.get_cursor()

        cursor.execute(
            """
            UPDATE files
            SET hash = ?,
                language = ?,
                size = ?,
                lines = ?,
                last_modified = ?,
                analysis_data = ?
            WHERE project_id = ?
              AND path = ?
            """,
            (
                file.hash,
                file.language,
                file.size,
                file.lines,
                file.last_modified,
                json.dumps(asdict(file.analysis), default=str) if file.analysis is not None else None,
                project_id,
                relative_path,
            ),
        )

        cursor.execute(
            """
            SELECT id
            FROM files
            WHERE project_id = ?
              AND path = ?
            """,
            (project_id, relative_path),
        )

        row = cursor.fetchone()
        return row["id"]

    def load_by_project(self, project_id: int, project_root: Path) -> list[FileIndex]:
        cursor = self.get_cursor()

        cursor.execute(
            """
            SELECT id, path, hash, language, size, lines, last_modified, analysis_data
            FROM files
            WHERE project_id = ?
            """,
            (project_id,),
        )

        rows = cursor.fetchall()
        files = []

        for row in rows:
            file = FileIndex(
                id=row["id"],
                path=project_root / row["path"],
                hash=row["hash"],
                language=row["language"],
                size=row["size"],
                lines=row["lines"],
                last_modified=row["last_modified"],
            )

            if row["analysis_data"]:
                try:
                    analysis_dict = json.loads(row["analysis_data"])
                    file.analysis = FileAnalysis.from_dict(analysis_dict)
                except Exception:
                    file.analysis = None

            files.append(file)

        return files
