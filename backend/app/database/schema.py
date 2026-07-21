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
        self.create_history_tables()
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

            file TEXT,

            parent TEXT,

            line INTEGER,

            end_line INTEGER,

            column INTEGER,

            return_type TEXT,

            decorators TEXT,

            type_hints TEXT,

            parameters TEXT,

            docstring TEXT,

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

    def create_history_tables(self):
        cursor = self.connection.cursor()

        # ── Review history (Sprint 8.1) ───────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS review_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_path TEXT NOT NULL,
            project_name TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            overall_score REAL DEFAULT 0,
            complexity REAL DEFAULT 0,
            maintainability REAL DEFAULT 0,
            readability REAL DEFAULT 0,
            architecture REAL DEFAULT 0,
            documentation REAL DEFAULT 0,
            testing REAL DEFAULT 0,
            total_files INTEGER DEFAULT 0,
            total_lines INTEGER DEFAULT 0,
            avg_complexity REAL DEFAULT 0,
            avg_function_length REAL DEFAULT 0,
            docstring_coverage REAL DEFAULT 0,
            duplicate_blocks INTEGER DEFAULT 0,
            summary TEXT DEFAULT ''
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS review_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'info',
            message TEXT NOT NULL,
            recommendation TEXT DEFAULT '',
            FOREIGN KEY(review_id)
                REFERENCES review_runs(id)
                ON DELETE CASCADE
        );
        """)

        # ── Decision history (Sprint 8.3) ─────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS engineering_problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            goal TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL DEFAULT '',
            complexity TEXT NOT NULL DEFAULT 'low',
            risk TEXT NOT NULL DEFAULT 'low',
            project_path TEXT DEFAULT '',
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            chosen_candidate_id INTEGER,
            summary TEXT DEFAULT ''
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidate_solutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_id INTEGER NOT NULL,
            problem_record_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            reasoning TEXT DEFAULT '',
            files_modified TEXT DEFAULT '',
            estimated_tokens INTEGER DEFAULT 0,
            estimated_runtime TEXT DEFAULT '',
            estimated_memory TEXT DEFAULT '',
            rank_score REAL DEFAULT 0,
            was_chosen INTEGER DEFAULT 0,
            generated_by TEXT DEFAULT 'mock',
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(problem_record_id)
                REFERENCES engineering_problems(id)
                ON DELETE CASCADE
        );
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidate_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate_solution_id INTEGER NOT NULL,
            overall_score REAL DEFAULT 0,
            complexity_score REAL DEFAULT 0,
            maintainability_score REAL DEFAULT 0,
            readability_score REAL DEFAULT 0,
            architecture_score REAL DEFAULT 0,
            documentation_score REAL DEFAULT 0,
            review_data TEXT DEFAULT '',
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(candidate_solution_id)
                REFERENCES candidate_solutions(id)
                ON DELETE CASCADE
        );
        """)

        # ── User preferences (Sprint 8.6) ─────────────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dimension TEXT NOT NULL UNIQUE,
            preference_weight REAL NOT NULL DEFAULT 0.5,
            sample_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        # ── Engineering knowledge base (Sprint 8.4) ────────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            observation TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            sample_count INTEGER NOT NULL DEFAULT 1,
            pattern_data TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)

        # ── Repository health snapshots (Sprint 8.7) ──────────────
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS health_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_path TEXT NOT NULL,
            overall_score REAL DEFAULT 0,
            complexity REAL DEFAULT 0,
            maintainability REAL DEFAULT 0,
            readability REAL DEFAULT 0,
            architecture REAL DEFAULT 0,
            documentation REAL DEFAULT 0,
            testing REAL DEFAULT 0,
            technical_debt_estimate REAL DEFAULT 0,
            snapshot_date TEXT NOT NULL DEFAULT (datetime('now')),
            notes TEXT DEFAULT ''
        );
        """)

        self.connection.commit()

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
    