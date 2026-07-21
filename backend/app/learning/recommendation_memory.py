"""Recommendation Memory (Sprint 8.6, 8.9) — learns user preferences over
time so EDITH can personalize future recommendations.

Key capability: "Have I solved this before?"
If yes: EDITH retrieves past solutions, compares, improves, then generates.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Optional

from app.core.config import logger
from app.history.decision_history import DecisionHistory
from app.history.review_history import ReviewHistory
from app.learning.knowledge_base import KnowledgeBase


# Default preferences before any data
DEFAULT_PREFERENCE = 0.5


class RecommendationMemory:
    """Learns user preferences from decision history and personalizes.

    Usage::

        memory = RecommendationMemory(connection, knowledge_base, decision_history)
        weights = memory.get_personalized_weights()
        # {"complexity": 0.15, "maintainability": 0.35, ...}
    """

    def __init__(
        self,
        connection: sqlite3.Connection,
        knowledge_base: KnowledgeBase,
        decision_history: DecisionHistory,
        review_history: ReviewHistory,
    ):
        self.conn = connection
        self._kb = knowledge_base
        self._dh = decision_history
        self._rh = review_history

    # ------------------------------------------------------------------
    # User preference learning (Sprint 8.6)
    # ------------------------------------------------------------------

    def get_personalized_weights(self) -> dict[str, float]:
        """Get personalized ranking weights based on past decisions.

        Returns weights that emphasize dimensions the user has historically
        preferred (based on which solutions were chosen).
        """
        cursor = self.conn.cursor()

        # Get stored preferences
        cursor.execute("SELECT dimension, preference_weight, sample_count FROM user_preferences ORDER BY sample_count DESC")
        stored = cursor.fetchall()

        if not stored:
            # Return the default balanced weights — no data yet
            return {
                "complexity": 0.20,
                "maintainability": 0.25,
                "readability": 0.20,
                "architecture": 0.20,
                "documentation": 0.10,
                "performance": 0.05,
            }

        total_weight = sum(row["preference_weight"] for row in stored)
        if total_weight <= 0:
            return {}

        return {
            row["dimension"]: round(row["preference_weight"] / total_weight, 3)
            for row in stored
        }

    def record_preference(
        self,
        dimension: str,
        chosen_score: float,
        rejected_score: float,
    ) -> None:
        """Record that the user chose this dimension's priority.

        Increases the preference weight for dimensions where the chosen
        solution scored higher.
        """
        cursor = self.conn.cursor()

        delta = chosen_score - rejected_score
        # Normalize delta to a 0-1 preference score
        weight_change = max(0, min(1, (delta + 100) / 200))

        cursor.execute(
            """
            INSERT INTO user_preferences (dimension, preference_weight, sample_count)
            VALUES (?, ?, 1)
            ON CONFLICT(dimension) DO UPDATE SET
                preference_weight = (preference_weight * sample_count + ?) / (sample_count + 1),
                sample_count = sample_count + 1,
                updated_at = datetime('now')
            """,
            (dimension, weight_change, weight_change),
        )
        self.conn.commit()

    def get_preference_summary(self) -> dict[str, float]:
        """Get a human-readable summary of learned preferences."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT dimension, preference_weight, sample_count FROM user_preferences ORDER BY sample_count DESC")
        rows = cursor.fetchall()
        return {
            row["dimension"]: {
                "weight": row["preference_weight"],
                "samples": row["sample_count"],
            }
            for row in rows
        }

    # ------------------------------------------------------------------
    # Engineering Memory (Sprint 8.9) — "Have I solved this before?"
    # ------------------------------------------------------------------

    def find_similar_problems(
        self, goal: str, question: str, limit: int = 5,
    ) -> list[dict]:
        """Find similar engineering problems in history.

        Matches by goal type and keyword overlap.
        """
        problems = self._dh.get_problems_by_goal(goal)
        question_lower = question.lower()
        question_words = set(question_lower.split())

        scored: list[tuple[float, dict]] = []

        for p in problems:
            # Simple keyword overlap score
            p_words = set(p.question.lower().split())
            overlap = len(question_words & p_words)
            if overlap > 0:
                score = overlap / max(len(question_words | p_words), 1)
                scored.append((
                    score,
                    {
                        "question": p.question,
                        "goal": p.goal,
                        "chosen_candidate_id": p.chosen_candidate_id,
                        "timestamp": p.timestamp,
                    },
                ))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def has_solved_before(self, goal: str, question: str) -> bool:
        """Quick check: has EDITH seen a similar problem before?"""
        similar = self.find_similar_problems(goal, question, limit=1)
        return len(similar) > 0 and similar[0].get("chosen_candidate_id") is not None
