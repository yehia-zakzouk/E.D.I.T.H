import sqlite3


class BaseRepository:
    """
    Base class for all repositories.
    Provides access to the database connection and helper methods.
    """

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def get_cursor(self) -> sqlite3.Cursor:
        """
        Returns a new cursor.
        Store it in a local variable inside each repository method.
        """
        return self.connection.cursor()

    def begin_transaction(self):
        """Begin a new transaction."""
        self.connection.execute("BEGIN")

    def commit(self):
        """Commit the current transaction."""
        self.connection.commit()

    def rollback(self):
        """Rollback the current transaction."""
        self.connection.rollback()

    def rollback_transaction(self):
        """Rollback the current transaction."""
        self.rollback()

    def close(self):
        """Close the database connection."""
        self.connection.close()