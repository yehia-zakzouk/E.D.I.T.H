"""Patch Reviewer (Sprint 9.4) — evaluates every patch through the Review
Engine, scoring the code before and after the change.

This is identical in principle to Sprint 7.3 (ReviewRunner), except we're
scoring **patches** instead of candidate solutions. Each patch's new code
is analyzed by the same ComplexityAnalyzer → MaintainabilityAnalyzer →
ReadabilityAnalyzer → ScoringEngine pipeline.

The result: every patch gets objective numbers showing whether it's an
improvement, a regression, or neutral.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.core.config import logger
from app.autonomous.models import Patch, PatchStatus

from app.review.metrics import FileMetrics, RepositoryMetrics
from app.review.analyzers.complexity import ComplexityAnalyzer
from app.review.analyzers.maintainability import MaintainabilityAnalyzer
from app.review.analyzers.readability import ReadabilityAnalyzer
from app.review.scoring import ScoringEngine


class PatchReviewer:
    """Scores patches by running the Review Engine on both old and new code.

    Usage::

        reviewer = PatchReviewer()
        patches = reviewer.review(patches)
        for patch in patches:
            print(patch.score_delta)  # +3.2 means improvement
    """

    def __init__(self):
        self._complexity = ComplexityAnalyzer()
        self._maintainability = MaintainabilityAnalyzer()
        self._readability = ReadabilityAnalyzer()
        self._scoring = ScoringEngine()

    def review(self, patches: list[Patch]) -> list[Patch]:
        """Score every patch by comparing old vs new code through the Review Engine.

        Populates:
            - ``patch.score_before`` — review score of the original code
            - ``patch.score_after`` — review score of the new code
            - ``patch.score_delta`` — difference (positive = improvement)
            - ``patch.dimension_deltas`` — per-dimension changes
        """
        logger.info("PatchReviewer: reviewing %d patches", len(patches))

        for patch in patches:
            try:
                self._review_single(patch)
            except Exception as e:
                logger.warning(
                    "PatchReviewer: failed to review patch for %s: %s",
                    patch.file_path,
                    e,
                )
                patch.score_before = 50.0
                patch.score_after = 50.0
                patch.score_delta = 0.0
                patch.dimension_deltas = {}

        return patches

    def _review_single(self, patch: Patch) -> None:
        """Score old vs new code for a single patch."""
        # ── Score original code ─────────────────────────────────────
        score_before = self._score_code(patch.original_code)
        # ── Score new code ──────────────────────────────────────────
        score_after = self._score_code(patch.new_code)

        # ── Compute deltas ──────────────────────────────────────────
        dims_before = {d.name: d.score for d in score_before.dimensions}
        dims_after = {d.name: d.score for d in score_after.dimensions}

        dimension_deltas: dict[str, float] = {}
        for dim in dims_after:
            before = dims_before.get(dim, 50.0)
            after = dims_after.get(dim, 50.0)
            dimension_deltas[dim] = round(after - before, 1)

        patch.score_before = score_before.overall
        patch.score_after = score_after.overall
        patch.score_delta = round(score_after.overall - score_before.overall, 1)
        patch.dimension_deltas = dimension_deltas

        # Determine status based on delta
        if patch.score_delta > 1.0:
            patch.status = PatchStatus.IMPROVES
        elif patch.score_delta < -1.0:
            patch.status = PatchStatus.REGRESSION
        else:
            patch.status = PatchStatus.NEUTRAL

        logger.debug(
            "PatchReviewer: %s → before=%.1f after=%.1f delta=%.1f (%s)",
            patch.file_path,
            patch.score_before,
            patch.score_after,
            patch.score_delta,
            patch.status.value,
        )

    def _score_code(self, code: str):
        """Run the Review Engine pipeline on a code string."""
        if not code.strip():
            return self._scoring.score(RepositoryMetrics(files=[]))

        file_path = Path("_patch_review.py")
        symbols = []

        # Complexity
        fm = self._complexity.analyze_file(
            file_path=file_path,
            source=code,
            symbols=symbols,
        )
        # Maintainability
        fm = self._maintainability.analyze_file(
            file_path=file_path,
            source=code,
            symbols=symbols,
            file_metrics=fm,
        )
        # Readability
        fm = self._readability.analyze_file(
            file_path=file_path,
            source=code,
            symbols=symbols,
            file_metrics=fm,
        )

        # Aggregate and score
        repo_metrics = RepositoryMetrics(files=[fm])
        repo_metrics.aggregate()
        return self._scoring.score(repo_metrics)
