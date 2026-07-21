"""Decision History (Sprint 8.3) — stores every generated engineering problem,
its candidate solutions, their reviews, and which solution was ultimately chosen.

Over time, EDITH builds a dataset of ``problem → candidates → choice`` decisions.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import logger
from app.decision.problem import EngineeringProblem
from app.decision.candidate import CandidateSolution


@dataclass
class ProblemRecord:
    """A stored engineering problem with its candidates."""
    id: int = 0
    problem_id: int = 0
    question: str = ""
    goal: str = ""
    scope: str = ""
    complexity: str = ""
    risk: str = ""
    project_path: str = ""
    timestamp: str = ""
    chosen_candidate_id: Optional[int] = None
    summary: str = ""


class DecisionHistory:
    """Persists and retrieves engineering decisions from the database."""

    def __init__(self, connection: sqlite3.Connection):
        self.conn = connection

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save_problem(
        self,
        problem: EngineeringProblem,
        project_path: str = "",
    ) -> int:
        """Save an engineering problem. Returns the record ID."""
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO engineering_problems (
                problem_id, question, goal, scope,
                complexity, risk, project_path, summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                problem.problem_id,
                problem.question,
                problem.goal.value,
                problem.scope.value,
                problem.complexity,
                problem.risk,
                project_path,
                problem.summary(),
            ),
        )
        record_id = cursor.lastrowid
        self.conn.commit()
        logger.debug(
            "DecisionHistory: saved problem #%d (record #%d)",
            problem.problem_id, record_id,
        )
        return record_id

    def save_candidates(
        self,
        problem_record_id: int,
        candidates: list[CandidateSolution],
        chosen_candidate_id: Optional[int] = None,
        generator_name: str = "mock",
    ) -> list[int]:
        """Save candidate solutions for a problem. Returns their record IDs."""
        cursor = self.conn.cursor()
        ids: list[int] = []

        for candidate in candidates:
            cursor.execute(
                """
                INSERT INTO candidate_solutions (
                    candidate_id, problem_record_id, title, description,
                    reasoning, files_modified, estimated_tokens,
                    estimated_runtime, estimated_memory, rank_score,
                    was_chosen, generated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.candidate_id,
                    problem_record_id,
                    candidate.title,
                    candidate.description,
                    candidate.reasoning,
                    json.dumps(candidate.files_modified),
                    candidate.estimated_tokens,
                    candidate.estimated_runtime,
                    candidate.estimated_memory,
                    candidate.rank_score,
                    1 if candidate.candidate_id == chosen_candidate_id else 0,
                    generator_name,
                ),
            )
            solution_id = cursor.lastrowid
            ids.append(solution_id)

            # Save the review result if it exists
            if candidate.review_result:
                self._save_candidate_review(solution_id, candidate)

            # Mark the chosen candidate on the problem record
            if candidate.candidate_id == chosen_candidate_id:
                cursor.execute(
                    "UPDATE engineering_problems SET chosen_candidate_id = ? WHERE id = ?",
                    (candidate.candidate_id, problem_record_id),
                )

        self.conn.commit()
        logger.debug(
            "DecisionHistory: saved %d candidates for problem record #%d",
            len(candidates), problem_record_id,
        )
        return ids

    def _save_candidate_review(
        self, solution_id: int, candidate: CandidateSolution,
    ) -> None:
        review = candidate.review_result or {}
        dims = review.get("dimensions", [])
        dim_map = {d["name"]: d["score"] for d in dims}

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO candidate_reviews (
                candidate_solution_id, overall_score,
                complexity_score, maintainability_score,
                readability_score, architecture_score,
                documentation_score, review_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                solution_id,
                review.get("overall", 0),
                dim_map.get("complexity", 0),
                dim_map.get("maintainability", 0),
                dim_map.get("readability", 0),
                dim_map.get("architecture", 0),
                dim_map.get("documentation", 0),
                json.dumps(review),
            ),
        )

    def mark_chosen(self, problem_record_id: int, candidate_id: int) -> None:
        """Mark a specific candidate as the chosen solution."""
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE engineering_problems SET chosen_candidate_id = ? WHERE id = ?",
            (candidate_id, problem_record_id),
        )
        cursor.execute(
            "UPDATE candidate_solutions SET was_chosen = 1 WHERE problem_record_id = ? AND candidate_id = ?",
            (problem_record_id, candidate_id),
        )
        cursor.execute(
            "UPDATE candidate_solutions SET was_chosen = 0 WHERE problem_record_id = ? AND candidate_id != ?",
            (problem_record_id, candidate_id),
        )
        self.conn.commit()

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def get_recent_problems(
        self, limit: int = 20, project_path: Optional[str] = None,
    ) -> list[ProblemRecord]:
        cursor = self.conn.cursor()
        if project_path:
            cursor.execute(
                """
                SELECT * FROM engineering_problems
                WHERE project_path = ?
                ORDER BY timestamp DESC LIMIT ?
                """,
                (project_path, limit),
            )
        else:
            cursor.execute(
                "SELECT * FROM engineering_problems ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        return [
            ProblemRecord(
                id=row["id"],
                problem_id=row["problem_id"],
                question=row["question"],
                goal=row["goal"],
                scope=row["scope"],
                complexity=row["complexity"],
                risk=row["risk"],
                project_path=row["project_path"],
                timestamp=row["timestamp"],
                chosen_candidate_id=row["chosen_candidate_id"],
                summary=row["summary"],
            )
            for row in cursor.fetchall()
        ]

    def get_problems_by_goal(self, goal: str) -> list[ProblemRecord]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM engineering_problems
            WHERE goal = ?
            ORDER BY timestamp DESC
            """,
            (goal,),
        )
        return [
            ProblemRecord(
                id=row["id"],
                problem_id=row["problem_id"],
                question=row["question"],
                goal=row["goal"],
                scope=row["scope"],
                complexity=row["complexity"],
                risk=row["risk"],
                project_path=row["project_path"],
                timestamp=row["timestamp"],
                chosen_candidate_id=row["chosen_candidate_id"],
                summary=row["summary"],
            )
            for row in cursor.fetchall()
        ]
