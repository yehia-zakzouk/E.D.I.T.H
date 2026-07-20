from app.database.repositories.base_repository import BaseRepository


class TechnologyRepository(BaseRepository):

    def save_many(self, project_id: int, technologies: list[tuple[str, str]]):
        cursor = self.get_cursor()

        cursor.execute(
            """
            DELETE FROM project_technologies
            WHERE project_id = ?
            """,
            (project_id,),
        )

        cursor.executemany(
            """
            INSERT INTO project_technologies (
                project_id,
                category,
                name
            )
            VALUES (?, ?, ?)
            """,
            [(project_id, category, name) for category, name in technologies],
        )


    def load_by_project(self, project_id: int) -> list[tuple[str, str]]:
        cursor = self.get_cursor()

        cursor.execute(
            """
            SELECT category, name
            FROM project_technologies
            WHERE project_id = ?
            """,
            (project_id,),
        )

        return [(row["category"], row["name"]) for row in cursor.fetchall()]
