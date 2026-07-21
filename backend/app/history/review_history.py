"""Review History (Sprint 8.1) — stores every repository review permanently.

Every run of the Review Engine saves its scores, strengths, weaknesses,
and recommendations to the database. Over time this builds a trend line
for every project.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.core.config import logger


@dataclass
class ReviewRunRecord:
    """A single review run stored in the database."""

    id: int = 0
    project_path: str = ""
    project_name: str = ""
    timestamp: str = ""
    overall_score: float = 0.0
    complexity: float = 0.0
    maintainability: float = 0.0
    readability: float = 0.0
    architecture: float = 0.0
    documentation: float = 0.0
    testing: float = 0.0
    total_files: int = 0
    total_lines: int = 0
    avg_complexity: float = 0.0
    avg_function_length: float = 0.0
    docstring_coverage: float = 0.0
    duplicate_blocks: int = 0
    summary: str = ""
    findings: list[dict] = field(default_factory=list)


@dataclass
class ReviewFinding:
    """A single finding (strength/weakness/recommendation)."""

    category: str = ""
    severity: str = "info"
    message: str = ""
    recommendation: str = ""


class ReviewHistory:
    """Persists and retrieves review runs from the database."""

    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_review(
        self,
        project_path: str,
        project_name: str,
        overall_score: float,
        dimension_scores: dict[str, float],
        strengths: list[str],
        weaknesses: list[str],
        recommendations: list[str],
        metrics: Optional[dict] = None,
    ) -> int:
        """Save a review run and its findings. Returns the review run ID."""
        metrics = metrics or {}
        cursor = self.conn.cursor()

        cursor.execute(
            """
            INSERT INTO review_runs (
                project_path, project_name,
                overall_score, complexity, maintainability,
                readability, architecture, documentation, testing,
                total_files, total_lines, avg_complexity,
                avg_function_length, docstring_coverage, duplicate_blocks,
                summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_path,
                project_name,
                overall_score,
                dimension_scores.get("complexity", 0),
                dimension_scores.get("maintainability", 0),
                dimension_scores.get("readability", 0),
                dimension_scores.get("architecture", 0),
                dimension_scores.get("documentation", 0),
                dimension_scores.get("testing", 0),
                metrics.get("total_files", 0),
                metrics.get("total_lines", 0),
                metrics.get("average_complexity", 0),
                metrics.get("average_function_length", 0),
                metrics.get("docstring_coverage", 0),
                metrics.get("duplicate_blocks", 0),
                json.dumps({
                    "strengths": strengths[:5],
                    "weaknesses": weaknesses[:5],
                    "recommendations": recommendations[:5],
                }),
            ),
        )
        review_id = cursor.lastrowid

        # Save findings
        for item in strengths:
            self._save_finding(review_id, "strength", "positive", item, "")
        for item in weaknesses:
            self._save_finding(review_id, "weakness", "negative", item, "")
        for item in recommendations:
            self._save_finding(review_id, "recommendation", "info", item, item)

        self.conn.commit()
        logger.debug("ReviewHistory: saved review #%d for %s", review_id, project_name)
        return review_id

    def _save_finding(
        self, review_id: int, category: str, severity: str,
        message: str, recommendation: str,
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO review_findings (review_id, category, severity, message, recommendation)
            VALUES (?, ?, ?, ?, ?)
            """,
            (review_id, category, severity, message, recommendation),
        )

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def get_reviews(
        self,
        project_path: Optional[str] = None,
        limit: int = 20,
    ) -> list[ReviewRunRecord]:
        """Get recent review runs, optionally filtered by project."""
        cursor = self.conn.cursor()

        if project_path:
            cursor.execute(
                """
                SELECT * FROM review_runs
                WHERE project_path = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (project_path, limit),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM review_runs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )

        records = []
        for row in cursor.fetchall():
            records.append(self._row_to_record(row))
        return records

    def get_latest_review(self, project_path: str) -> Optional[ReviewRunRecord]:
        """Get the most recent review for a project."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM review_runs
            WHERE project_path = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (project_path,),
        )
        row = cursor.fetchone()
        return self._row_to_record(row) if row else None

    def get_previous_review(self, project_path: str) -> Optional[ReviewRunRecord]:
        """Get the second-most-recent review (for diff comparisons)."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM review_runs
            WHERE project_path = ?
            ORDER BY timestamp DESC
            LIMIT 1 OFFSET 1
            """,
            (project_path,),
        )
        row = cursor.fetchone()
        return self._row_to_record(row) if row else None

    def get_review_count(self, project_path: Optional[str] = None) -> int:
        cursor = self.conn.cursor()
        if project_path:
            cursor.execute(
                "SELECT COUNT(*) FROM review_runs WHERE project_path = ?",
                (project_path,),
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM review_runs")
        return cursor.fetchone()[0]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _row_to_record(self, row: sqlite3.Row) -> ReviewRunRecord:
        return ReviewRunRecord(
            id=row["id"],
            project_path=row["project_path"],
            project_name=row["project_name"],
            timestamp=row["timestamp"],
            overall_score=row["overall_score"],
            complexity=row["complexity"],
            maintainability=row["maintainability"],
            readability=row["readability"],
            architecture=row["architecture"],
            documentation=row["documentation"],
            testing=row["testing"],
            total_files=row["total_files"],
            total_lines=row["total_lines"],
            avg_complexity=row["avg_complexity"],
            avg_function_length=row["avg_function_length"],
            docstring_coverage=row["docstring_coverage"],
            duplicate_blocks=row["duplicate_blocks"],
            summary=row["summary"],
        )
