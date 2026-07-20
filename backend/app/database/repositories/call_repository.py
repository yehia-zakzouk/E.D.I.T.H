from app.database.repositories.base_repository import BaseRepository


class CallRepository(BaseRepository):

    def save_many(self, file_id: int, calls: list[tuple[str, str, int | None]]):
        cursor = self.get_cursor()

        cursor.execute(
            """
            DELETE FROM calls
            WHERE file_id = ?
            """,
            (file_id,),
        )

        cursor.executemany(
            """
            INSERT INTO calls (
                file_id,
                caller,
                callee,
                line
            )
            VALUES (?, ?, ?, ?)
            """,
            [(file_id, caller, callee, line) for caller, callee, line in calls],
        )

    def load_by_file(self, file_id: int) -> list[tuple[str, str, int | None]]:
        cursor = self.get_cursor()

        cursor.execute(
            """
            SELECT caller, callee, line
            FROM calls
            WHERE file_id = ?
            """,
            (file_id,),
        )

        return [(row["caller"], row["callee"], row["line"]) for row in cursor.fetchall()]

    def delete_by_file(self, file_id: int):
        cursor = self.get_cursor()

        cursor.execute(
            """
            DELETE FROM calls
            WHERE file_id = ?
            """,
            (file_id,),
        )
