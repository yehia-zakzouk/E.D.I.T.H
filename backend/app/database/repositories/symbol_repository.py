import json
from typing import Optional

from app.database.repositories.base_repository import BaseRepository


class SymbolRepository(BaseRepository):

    def save(
        self,
        file_id: int,
        name: str,
        kind: str,
        file: Optional[str] = None,
        parent: Optional[str] = None,
        line: Optional[int] = None,
        end_line: Optional[int] = None,
        column: Optional[int] = None,
        return_type: Optional[str] = None,
        decorators: Optional[list[str]] = None,
        type_hints: Optional[list[str]] = None,
        parameters: Optional[list[dict]] = None,
        docstring: Optional[str] = None,
    ) -> int:
        cursor = self.get_cursor()

        cursor.execute(
            """
            INSERT INTO symbols (
                file_id,
                name,
                kind,
                file,
                parent,
                line,
                end_line,
                column,
                return_type,
                decorators,
                type_hints,
                parameters,
                docstring
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                file_id,
                name,
                kind,
                file,
                parent,
                line,
                end_line,
                column,
                return_type,
                json.dumps(decorators or []),
                json.dumps(type_hints or []),
                json.dumps(parameters or []),
                docstring,
            ),
        )

        return cursor.lastrowid

    def save_many(
        self,
        file_id: int,
        symbols: list[
            tuple[
                str,
                str,
                Optional[str],
                Optional[str],
                Optional[int],
                Optional[int],
                Optional[int],
                Optional[str],
                list[str],
                list[str],
                list[dict],
                Optional[str],
            ]
        ],
    ):
        for (
            name,
            kind,
            file,
            parent,
            line,
            end_line,
            column,
            return_type,
            decorators,
            type_hints,
            parameters,
            docstring,
        ) in symbols:
            self.save(
                file_id,
                name,
                kind,
                file,
                parent,
                line,
                end_line,
                column,
                return_type,
                decorators,
                type_hints,
                parameters,
                docstring,
            )

    def load_by_file(self, file_id: int) -> list[tuple[str, str, Optional[str], Optional[str], Optional[int], Optional[int], Optional[int], Optional[str], list[str], list[str], list[dict], Optional[str]]]:
        cursor = self.get_cursor()

        cursor.execute(
            """
            SELECT name, kind, file, parent, line, end_line, column, return_type, decorators, type_hints, parameters, docstring
            FROM symbols
            WHERE file_id = ?
            """,
            (file_id,),
        )

        return [
            (
                row["name"],
                row["kind"],
                row["file"],
                row["parent"],
                row["line"],
                row["end_line"],
                row["column"],
                row["return_type"],
                json.loads(row["decorators"] or "[]"),
                json.loads(row["type_hints"] or "[]"),
                json.loads(row["parameters"] or "[]"),
                row["docstring"],
            )
            for row in cursor.fetchall()
        ]

    def delete_by_file(self, file_id: int):
        cursor = self.get_cursor()

        cursor.execute(
            """
            DELETE FROM symbols
            WHERE file_id = ?
            """,
            (file_id,),
        )
