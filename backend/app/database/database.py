import sqlite3

from app.core.config import config
from app.database.schema import DatabaseSchema


class DatabaseManager:

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(config.db_path)
        self.connection = None

    def connect(self):
        from pathlib import Path

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        if self.connection is None:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row

            self.connection.execute("PRAGMA foreign_keys = ON;")

        return self.connection

    def initialize(self):
        connection = self.connect()

        schema = DatabaseSchema(connection)
        schema.create_tables()

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None