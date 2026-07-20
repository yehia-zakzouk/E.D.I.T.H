from typing import Optional

from app.database.repositories.base_repository import BaseRepository


class SymbolRepository(BaseRepository):

    def save(self, file_id: int, name: str, kind: str, line: Optional[int] = None) -> int:
        cursor = self.get_cursor()

        cursor.execute(
            """
            INSERT INTO symbols (
                file_id,
                name,
                kind,
                line
            )
            VALUES (?, ?, ?, ?)
            """,
            (file_id, name, kind, line),
        )

        self.commit()

        return cursor.lastrowid

    def save_many(self, file_id: int, symbols: list[tuple[str, str, Optional[int]]]):
        for name, kind, line in symbols:
            self.save(file_id, name, kind, line)

    def delete_by_file(self, file_id: int):
        cursor = self.get_cursor()

        cursor.execute(
            """
            DELETE FROM symbols
            WHERE file_id = ?
            """,
            (file_id,),
        )

        self.commit()
