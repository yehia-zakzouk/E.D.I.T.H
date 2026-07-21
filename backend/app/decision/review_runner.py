"""Review Runner (Sprint 7.3) — evaluates every CandidateSolution through the
existing Review Engine, populating ``review_result`` and ``dimension_scores``.

Every candidate now has objective numbers, computed by the **same analyzers**
that evaluate the rest of the repository.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

from app.core.config import logger
from app.decision.candidate import CandidateSolution

from app.review.metrics import FileMetrics, RepositoryMetrics
from app.review.analyzers.complexity import ComplexityAnalyzer
from app.review.analyzers.maintainability import MaintainabilityAnalyzer
from app.review.analyzers.readability import ReadabilityAnalyzer
from app.review.scoring import ScoringEngine


class ReviewRunner:
    """Evaluates all candidates through the Review Engine.

    Usage::

        runner = ReviewRunner()
        candidates = runner.evaluate(candidates)
        for c in candidates:
            print(c.dimension_scores)  # {"complexity": 85, ...}
    """

    def __init__(self):
        self._complexity = ComplexityAnalyzer()
        self._maintainability = MaintainabilityAnalyzer()
        self._readability = ReadabilityAnalyzer()
        self._scoring = ScoringEngine()

    def evaluate(
        self,
        candidates: list[CandidateSolution],
    ) -> list[CandidateSolution]:
        """Run the review engine on every candidate's code.

        Populates:
            - ``candidate.review_result`` → full review dict
            - ``candidate.dimension_scores`` → per-dimension scores
        """
        logger.info("ReviewRunner: evaluating %d candidates", len(candidates))

        for candidate in candidates:
            try:
                self._evaluate_single(candidate)
            except Exception as e:
                logger.warning(
                    "ReviewRunner: failed to evaluate candidate #%d '%s': %s",
                    candidate.candidate_id,
                    candidate.title,
                    e,
                )
                candidate.review_result = {"error": str(e)}
                candidate.dimension_scores = {}

        return candidates

    def _evaluate_single(self, candidate: CandidateSolution) -> None:
        """Run all Review Engine analyzers against a single candidate's code.

        Creates a temporary ``FileMetrics`` from the candidate's source code,
        runs it through ComplexityAnalyzer → MaintainabilityAnalyzer →
        ReadabilityAnalyzer, aggregates into a single-file RepositoryMetrics,
        then runs the ScoringEngine to produce dimension scores.
        """
        source = candidate.code
        if not source.strip():
            candidate.review_result = {"error": "No code to review"}
            candidate.dimension_scores = {}
            return

        # Create a virtual file path for the analyzers
        file_path = Path(f"candidate_{candidate.candidate_id}.py")
        symbols = []  # Candidate code is raw — no pre-extracted symbols

        # ── 1. Complexity analysis ─────────────────────────────────
        fm = self._complexity.analyze_file(
            file_path=file_path,
            source=source,
            symbols=symbols,
        )

        # ── 2. Maintainability analysis ────────────────────────────
        fm = self._maintainability.analyze_file(
            file_path=file_path,
            source=source,
            symbols=symbols,
            file_metrics=fm,
        )

        # ── 3. Readability analysis ────────────────────────────────
        fm = self._readability.analyze_file(
            file_path=file_path,
            source=source,
            symbols=symbols,
            file_metrics=fm,
        )

        # ── 4. Aggregate into repository metrics (single file) ─────
        repo_metrics = RepositoryMetrics(files=[fm])
        repo_metrics.aggregate()

        # ── 5. Score via the ScoringEngine ─────────────────────────
        score = self._scoring.score(repo_metrics)

        # ── 6. Extract dimension scores ────────────────────────────
        dimension_scores: dict[str, float] = {}
        for dim in score.dimensions:
            dimension_scores[dim.name] = dim.score

        candidate.dimension_scores = dimension_scores
        candidate.review_result = {
            "overall": score.overall,
            "rating": score.rating,
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "weight": d.weight,
                    "rating": d.rating,
                }
                for d in score.dimensions
            ],
            "strengths": score.strengths,
            "weaknesses": score.weaknesses,
            "metrics": {
                "lines_of_code": fm.code_lines,
                "total_lines": fm.lines,
                "comment_lines": fm.comment_lines,
                "function_count": fm.function_count,
                "class_count": fm.class_count,
                "avg_complexity": round(fm.average_complexity, 2),
                "maintainability_index": fm.maintainability_index,
                "max_line_length": fm.max_line_length,
                "files_modified": len(candidate.files_modified),
                "docstring_coverage": round(fm.docstring_coverage, 2),
            },
        }

        logger.debug(
            "ReviewRunner: candidate #%d '%s' → overall=%.1f rating=%s",
            candidate.candidate_id,
            candidate.title,
            score.overall,
            score.rating,
        )
