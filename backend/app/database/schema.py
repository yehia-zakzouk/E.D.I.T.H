import sqlite3


class DatabaseSchema:
    """
    Responsible for creating and maintaining the EDITH database schema.
    """

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def create_tables(self):
        """Create all database tables."""
        self.create_projects_table()
        self.create_files_table()
        self.create_symbols_table()
        self.create_relationships_table()
        self.create_calls_table()
        self.create_inheritance_table()
        self.create_metrics_table()
        self.create_project_technologies_table()
        self.create_indexes()

        self.connection.commit()

    def create_projects_table(self):
        cursor = self.connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            name TEXT NOT NULL,

            path TEXT NOT NULL UNIQUE,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            last_scan TIMESTAMP,

            docker INTEGER DEFAULT 0,

            git INTEGER DEFAULT 0
        );
        """)

    def create_files_table(self):
        cursor = self.connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            project_id INTEGER NOT NULL,

            path TEXT NOT NULL,

            hash TEXT NOT NULL,

            language TEXT,

            size INTEGER,

            lines INTEGER,

            last_modified REAL,

            analysis_data TEXT,

            FOREIGN KEY(project_id)
                REFERENCES projects(id)
                ON DELETE CASCADE
        );
        """)

    def create_symbols_table(self):
        cursor = self.connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            file_id INTEGER NOT NULL,

            name TEXT NOT NULL,

            kind TEXT NOT NULL,

            line INTEGER,

            FOREIGN KEY(file_id)
                REFERENCES files(id)
                ON DELETE CASCADE
        );
        """)

    def create_relationships_table(self):
        cursor = self.connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            project_id INTEGER NOT NULL,

            source_file_id INTEGER NOT NULL,

            target_file_id INTEGER NOT NULL,

            relation TEXT NOT NULL,

            FOREIGN KEY(project_id)
                REFERENCES projects(id)
                ON DELETE CASCADE,

            FOREIGN KEY(source_file_id)
                REFERENCES files(id)
                ON DELETE CASCADE,

            FOREIGN KEY(target_file_id)
                REFERENCES files(id)
                ON DELETE CASCADE
        );
        """)

    def create_calls_table(self):
        cursor = self.connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            file_id INTEGER NOT NULL,

            caller TEXT NOT NULL,

            callee TEXT NOT NULL,

            line INTEGER,

            FOREIGN KEY(file_id)
                REFERENCES files(id)
                ON DELETE CASCADE
        );
        """)

    def create_inheritance_table(self):
        cursor = self.connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS inheritance_relations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            file_id INTEGER NOT NULL,

            child TEXT NOT NULL,

            parent TEXT NOT NULL,

            line INTEGER,

            FOREIGN KEY(file_id)
                REFERENCES files(id)
                ON DELETE CASCADE
        );
        """)

    def create_metrics_table(self):
        cursor = self.connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            file_id INTEGER NOT NULL,

            todo_count INTEGER DEFAULT 0,

            function_count INTEGER DEFAULT 0,

            class_count INTEGER DEFAULT 0,

            complexity REAL DEFAULT 0,

            FOREIGN KEY(file_id)
                REFERENCES files(id)
                ON DELETE CASCADE
        );
        """)
    def create_project_technologies_table(self):
        cursor = self.connection.cursor()

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS project_technologies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            project_id INTEGER NOT NULL,

            category TEXT NOT NULL,

            name TEXT NOT NULL,

            FOREIGN KEY(project_id)
                REFERENCES projects(id)
                ON DELETE CASCADE
        );
        """)

    def create_indexes(self):
        cursor = self.connection.cursor()

        cursor.execute("""
         CREATE INDEX IF NOT EXISTS idx_project_path
         ON projects(path);
         """)

        cursor.execute("""
         CREATE UNIQUE INDEX IF NOT EXISTS idx_file_project_path
         ON files(project_id, path);
         """)

        cursor.execute("""
         CREATE INDEX IF NOT EXISTS idx_file_project
         ON files(project_id);
         """)

        cursor.execute("""
         CREATE INDEX IF NOT EXISTS idx_symbol_file
         ON symbols(file_id);
         """)

        cursor.execute("""
         CREATE INDEX IF NOT EXISTS idx_relationships_project
         ON relationships(project_id);
         """)

        cursor.execute("""
         CREATE INDEX IF NOT EXISTS idx_relationships_source_file
         ON relationships(source_file_id);
         """)

        cursor.execute("""
         CREATE INDEX IF NOT EXISTS idx_relationships_target_file
         ON relationships(target_file_id);
         """)

        cursor.execute("""
         CREATE INDEX IF NOT EXISTS idx_calls_file
         ON calls(file_id);
         """)

        cursor.execute("""
         CREATE INDEX IF NOT EXISTS idx_inheritance_file
         ON inheritance_relations(file_id);
         """)

        cursor.execute("""
         CREATE INDEX IF NOT EXISTS idx_project_technologies_project
         ON project_technologies(project_id);
         """)

        cursor.execute("""
         CREATE INDEX IF NOT EXISTS idx_project_technologies_name
         ON project_technologies(name);
        """)
    