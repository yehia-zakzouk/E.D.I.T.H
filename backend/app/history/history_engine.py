"""History Engine — the main orchestrator for EDITH's continuous learning layer.

Connects to the database and provides a unified API for saving and
retrieving review history, decision history, and trends.
"""

from __future__ import annotations

import sqlite3
from typing import Optional

from app.core.config import config, logger
from app.database.database import DatabaseManager
from app.history.review_history import ReviewHistory, ReviewRunRecord
from app.history.decision_history import DecisionHistory
from app.history.trend_analyzer import TrendAnalyzer, TrendReport
from app.decision.problem import EngineeringProblem
from app.decision.candidate import CandidateSolution


class HistoryEngine:
    """Unified API for EDITH's persistent history.

    Auto-initializes the database schema on first use.

    Usage::

        engine = HistoryEngine()
        engine.save_review(...)
        report = engine.get_trends(project_path)
        print(report.text())
    """

    def __init__(self, connection: Optional[sqlite3.Connection] = None):
        self._db: Optional[DatabaseManager] = None
        self._owns_connection = connection is None

        if connection is None:
            self._db = DatabaseManager()
            try:
                self._db.initialize()
                connection = self._db.connection
            except Exception as e:
                logger.warning("HistoryEngine: DB init failed (%s)", e)
                connection = None
        else:
            connection = connection

        self.conn = connection
        self.review_history = ReviewHistory(connection) if connection else None
        self.decision_history = DecisionHistory(connection) if connection else None
        self.trend_analyzer = TrendAnalyzer(self.review_history) if connection else None

    def _check_ready(self) -> bool:
        """Check if the database is ready for operations."""
        if self.conn is None:
            logger.warning("HistoryEngine: database not available")
            return False
        return True

    # ------------------------------------------------------------------
    # Review History (Sprint 8.1)
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
        if not self._check_ready():
            return -1
        return self.review_history.save_review(
            project_path, project_name, overall_score,
            dimension_scores, strengths, weaknesses,
            recommendations, metrics,
        )

    def get_recent_reviews(
        self, project_path: Optional[str] = None, limit: int = 20,
    ) -> list[ReviewRunRecord]:
        if not self._check_ready():
            return []
        return self.review_history.get_reviews(project_path, limit)

    # ------------------------------------------------------------------
    # Decision History (Sprint 8.3)
    # ------------------------------------------------------------------

    def save_problem(
        self, problem: EngineeringProblem, project_path: str = "",
    ) -> int:
        if not self._check_ready():
            return -1
        return self.decision_history.save_problem(problem, project_path)

    def save_candidates(
        self,
        problem_record_id: int,
        candidates: list[CandidateSolution],
        chosen_candidate_id: Optional[int] = None,
        generator_name: str = "mock",
    ) -> list[int]:
        if not self._check_ready():
            return []
        return self.decision_history.save_candidates(
            problem_record_id, candidates, chosen_candidate_id, generator_name,
        )

    def mark_chosen(self, problem_record_id: int, candidate_id: int) -> None:
        if self._check_ready():
            self.decision_history.mark_chosen(problem_record_id, candidate_id)

    # ------------------------------------------------------------------
    # Trends (Sprint 8.2)
    # ------------------------------------------------------------------

    def get_trends(self, project_path: str) -> Optional[TrendReport]:
        if not self._check_ready():
            return TrendReport(project_path=project_path)
        return self.trend_analyzer.compare_latest(project_path)

    # ------------------------------------------------------------------
    # Improvement History (Sprint 9)
    # ------------------------------------------------------------------

    def save_improvement(
        self,
        project_path: str,
        project_name: str,
        opportunities_found: int,
        patches_generated: int,
        patches_safe: int,
        score_before: float,
        score_after: float,
        details: dict,
    ) -> int:
        """Record an autonomous improvement run."""
        if not self._check_ready():
            return -1
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO review_runs (
                    project_path, project_name, overall_score,
                    complexity, maintainability, readability,
                    architecture, documentation, testing,
                    total_files, total_lines, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (
                    project_path,
                    project_name,
                    score_before,
                    0,  # individual dimension placeholders
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                ),
            )
            review_id = cursor.lastrowid

            # Store the improvement metadata as a finding
            summary = (
                f"Autonomous improvement: {opportunities_found} opportunities, "
                f"{patches_generated} patches, {patches_safe} safe, "
                f"score {score_before:.0f} → {score_after:.0f}"
            )
            cursor.execute(
                """
                INSERT INTO review_findings (review_id, category, severity, message, recommendation)
                VALUES (?, ?, ?, ?, ?)
                """,
                (review_id, "autonomous_improvement", "info", summary, str(details)),
            )

            self.conn.commit()
            logger.debug("Saved improvement run for %s", project_path)
            return review_id
        except Exception as e:
            logger.warning("Failed to save improvement history: %s", e)
            return -1

    def get_history_count(self) -> int:
        if not self._check_ready():
            return 0
        return self.review_history.get_review_count()
