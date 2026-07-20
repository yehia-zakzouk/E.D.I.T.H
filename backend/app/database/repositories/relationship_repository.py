from app.database.repositories.base_repository import BaseRepository


class RelationshipRepository(BaseRepository):

    def save_many(self, project_id: int, relationships: list[tuple[int, int, str]]):
        cursor = self.get_cursor()

        cursor.execute(
            """
            DELETE FROM relationships
            WHERE project_id = ?
            """,
            (project_id,),
        )

        cursor.executemany(
            """
            INSERT INTO relationships (
                project_id,
                source_file_id,
                target_file_id,
                relation
            )
            VALUES (?, ?, ?, ?)
            """,
            [(project_id, source_id, target_id, relation) for source_id, target_id, relation in relationships],
        )

        self.commit()

    def load_by_project(self, project_id: int) -> list[tuple[int, int, str]]:
        cursor = self.get_cursor()

        cursor.execute(
            """
            SELECT source_file_id, target_file_id, relation
            FROM relationships
            WHERE project_id = ?
            """,
            (project_id,),
        )

        return [(row["source_file_id"], row["target_file_id"], row["relation"]) for row in cursor.fetchall()]
