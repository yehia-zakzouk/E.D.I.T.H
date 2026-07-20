from typing import Dict, Optional, Union

from app.database.repositories.base_repository import BaseRepository


class MetricsRepository(BaseRepository):

    def save(self, file_id: int, todo_count: int, function_count: int, class_count: int, complexity: float):
        cursor = self.get_cursor()

        if self.exists(file_id):
            cursor.execute(
                """
                UPDATE metrics
                SET todo_count = ?,
                    function_count = ?,
                    class_count = ?,
                    complexity = ?
                WHERE file_id = ?
                """,
                (todo_count, function_count, class_count, complexity, file_id),
            )
        else:
            cursor.execute(
                """
                INSERT INTO metrics (
                    file_id,
                    todo_count,
                    function_count,
                    class_count,
                    complexity
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (file_id, todo_count, function_count, class_count, complexity),
            )


    def exists(self, file_id: int) -> bool:
        cursor = self.get_cursor()

        cursor.execute(
            """
            SELECT 1
            FROM metrics
            WHERE file_id = ?
            """,
            (file_id,),
        )

        return cursor.fetchone() is not None

    def load_by_file(self, file_id: int) -> Optional[Dict[str, Union[float, int]]]:
        cursor = self.get_cursor()

        cursor.execute(
            """
            SELECT todo_count, function_count, class_count, complexity
            FROM metrics
            WHERE file_id = ?
            """,
            (file_id,),
        )

        row = cursor.fetchone()
        if row is None:
            return None

        return {
            "todo_count": row["todo_count"],
            "function_count": row["function_count"],
            "class_count": row["class_count"],
            "complexity": row["complexity"],
        }
