from app.database.repositories.base_repository import BaseRepository


class InheritanceRepository(BaseRepository):

    def save_many(self, file_id: int, inheritance_relations: list[tuple[str, str, int | None]]):
        cursor = self.get_cursor()

        cursor.execute(
            """
            DELETE FROM inheritance_relations
            WHERE file_id = ?
            """,
            (file_id,),
        )

        cursor.executemany(
            """
            INSERT INTO inheritance_relations (
                file_id,
                child,
                parent,
                line
            )
            VALUES (?, ?, ?, ?)
            """,
            [
                (file_id, child, parent, line)
                for child, parent, line in inheritance_relations
            ],
        )

    def load_by_file(self, file_id: int) -> list[tuple[str, str, int | None]]:
        cursor = self.get_cursor()

        cursor.execute(
            """
            SELECT child, parent, line
            FROM inheritance_relations
            WHERE file_id = ?
            """,
            (file_id,),
        )

        return [(row["child"], row["parent"], row["line"]) for row in cursor.fetchall()]

    def delete_by_file(self, file_id: int):
        cursor = self.get_cursor()

        cursor.execute(
            """
            DELETE FROM inheritance_relations
            WHERE file_id = ?
            """,
            (file_id,),
        )
