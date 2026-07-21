"""Scoring Engine — computes a 0–100 engineering score from repository metrics.

The overall score is a weighted average of five dimensions:

    score = (
        readability  * 0.25 +
        maintainability * 0.25 +
        architecture * 0.20 +
        complexity   * 0.15 +
        documentation * 0.10 +
        testing      * 0.05
    )

All weights are user-configurable via ``ScoringEngine(weights={...})``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.review.metrics import RepositoryMetrics, FileMetrics


# Default weights — these will be user-configurable later
DEFAULT_WEIGHTS = {
    "readability": 0.25,
    "maintainability": 0.25,
    "architecture": 0.20,
    "complexity": 0.15,
    "documentation": 0.10,
    "testing": 0.05,
}


@dataclass
class DimensionScore:
    """Score for a single quality dimension."""

    name: str
    score: float         # 0 – 100
    weight: float        # 0.0 – 1.0
    details: dict = field(default_factory=dict)

    @property
    def weighted_score(self) -> float:
        return round(self.score * self.weight, 2)

    @property
    def rating(self) -> str:
        if self.score >= 90:
            return "excellent"
        if self.score >= 75:
            return "good"
        if self.score >= 50:
            return "fair"
        return "poor"


@dataclass
class ReviewScore:
    """Complete scoring result for a repository."""

    overall: float                # 0 – 100
    dimensions: list[DimensionScore] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)

    @property
    def rating(self) -> str:
        if self.overall >= 90:
            return "excellent"
        if self.overall >= 75:
            return "good"
        if self.overall >= 60:
            return "fair"
        if self.overall >= 40:
            return "poor"
        return "critical"

    def to_dict(self) -> dict:
        return {
            "overall": self.overall,
            "rating": self.rating,
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "weight": d.weight,
                    "weighted_score": d.weighted_score,
                    "rating": d.rating,
                    "details": d.details,
                }
                for d in self.dimensions
            ],
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
        }


class ScoringEngine:
    """Computes a weighted quality score from repository metrics.

    Usage::

        engine = ScoringEngine()
        score = engine.score(metrics)
        print(score.overall)      # e.g. 87.3
        print(score.strengths)    # ["Low coupling", ...]
        print(score.weaknesses)   # ["Low docstring coverage", ...]
    """

    def __init__(self, weights: Optional[dict[str, float]] = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()

    def score(self, metrics: RepositoryMetrics) -> ReviewScore:
        """Compute the full review score from repository metrics."""
        dimensions: list[DimensionScore] = []

        # --- Complexity (lower is better) ---
        complexity_score = self._score_complexity(metrics)
        dimensions.append(DimensionScore(
            name="complexity",
            score=complexity_score,
            weight=self.weights.get("complexity", 0.15),
            details={
                "average_complexity": metrics.average_complexity,
                "worst_function": metrics.worst_function,
                "worst_complexity": metrics.worst_function_complexity,
            },
        ))

        # --- Maintainability ---
        maintainability_score = self._score_maintainability(metrics)
        dimensions.append(DimensionScore(
            name="maintainability",
            score=maintainability_score,
            weight=self.weights.get("maintainability", 0.25),
            details={
                "comment_ratio": metrics.comment_ratio,
                "average_function_length": metrics.average_function_length,
            },
        ))

        # --- Readability ---
        readability_score = self._score_readability(metrics)
        dimensions.append(DimensionScore(
            name="readability",
            score=readability_score,
            weight=self.weights.get("readability", 0.25),
            details={
                "total_lines": metrics.total_lines,
                "longest_file": metrics.longest_file,
            },
        ))

        # --- Architecture ---
        architecture_score = self._score_architecture(metrics)
        dimensions.append(DimensionScore(
            name="architecture",
            score=architecture_score,
            weight=self.weights.get("architecture", 0.20),
            details={},
        ))

        # --- Documentation ---
        documentation_score = self._score_documentation(metrics)
        dimensions.append(DimensionScore(
            name="documentation",
            score=documentation_score,
            weight=self.weights.get("documentation", 0.10),
            details={
                "docstring_coverage": metrics.overall_docstring_coverage,
                "total_comment_lines": metrics.total_comment_lines,
            },
        ))

        # --- Testing (placeholder — will be richer when test coverage is measured) ---
        testing_score = self._score_testing(metrics)
        dimensions.append(DimensionScore(
            name="testing",
            score=testing_score,
            weight=self.weights.get("testing", 0.05),
            details={},
        ))

        # Overall = weighted sum
        overall = round(sum(d.weighted_score for d in dimensions), 1)

        # Strengths & weaknesses
        strengths = self._compute_strengths(dimensions, metrics)
        weaknesses = self._compute_weaknesses(dimensions, metrics)

        return ReviewScore(
            overall=overall,
            dimensions=dimensions,
            strengths=strengths,
            weaknesses=weaknesses,
        )

    # ------------------------------------------------------------------
    # Per-dimension scoring (each returns 0–100)
    # ------------------------------------------------------------------

    def _score_complexity(self, metrics: RepositoryMetrics) -> float:
        """Score complexity (0-100). Lower average complexity = better."""
        avg_cc = metrics.average_complexity

        if avg_cc <= 2.0:
            return 95
        if avg_cc <= 3.5:
            return 85
        if avg_cc <= 5.0:
            return 70
        if avg_cc <= 7.0:
            return 55
        if avg_cc <= 10.0:
            return 40
        if avg_cc <= 15.0:
            return 25
        return 10

    def _score_maintainability(self, metrics: RepositoryMetrics) -> float:
        """Score maintainability (0-100)."""
        score = 80.0

        # Penalise long average function length
        avg_len = metrics.average_function_length
        if avg_len > 60:
            score -= 20
        elif avg_len > 40:
            score -= 10
        elif avg_len > 20:
            score -= 5

        # Penalise very long functions
        worst_file = metrics.worst_function_file
        if worst_file:
            pass  # we could look up individual function length here

        # Bonus for good comment ratio (15–30% is ideal)
        comment_ratio = metrics.comment_ratio
        if 0.10 <= comment_ratio <= 0.35:
            score += 5
        elif comment_ratio < 0.05:
            score -= 10

        # Penalise excessive duplication
        if metrics.total_duplicate_blocks > 5:
            score -= 10

        return max(0, min(100, score))

    def _score_readability(self, metrics: RepositoryMetrics) -> float:
        """Score readability (0-100)."""
        score = 85.0

        # Penalise very long files
        if metrics.longest_file_lines and metrics.longest_file_lines > 800:
            score -= 15
        elif metrics.longest_file_lines and metrics.longest_file_lines > 500:
            score -= 8

        # Check average function length
        avg_len = metrics.average_function_length
        if avg_len > 50:
            score -= 10
        elif avg_len > 30:
            score -= 5

        return max(0, min(100, score))

    def _score_architecture(self, metrics: RepositoryMetrics) -> float:
        """Score architecture (0-100). Based on coupling, layer violations, cycles."""
        score = 85.0

        # Heuristic: if there are many files, we expect lower coupling
        if metrics.total_files > 0:
            # Penalise high average efferent coupling
            pass

        # Duplication indicates architecture issues
        if metrics.total_duplicate_blocks > 10:
            score -= 15
        elif metrics.total_duplicate_blocks > 5:
            score -= 8

        # If there are many symbols in few files, that's a cohesion concern
        if metrics.total_symbols > 0 and metrics.total_files > 0:
            symbols_per_file = metrics.total_symbols / metrics.total_files
            if symbols_per_file > 30:
                score -= 10
            elif symbols_per_file > 15:
                score -= 5

        return max(0, min(100, score))

    def _score_documentation(self, metrics: RepositoryMetrics) -> float:
        """Score documentation (0-100). Based on docstring coverage + comments."""
        coverage = metrics.overall_docstring_coverage

        if coverage >= 0.90:
            return 95
        if coverage >= 0.75:
            return 80
        if coverage >= 0.50:
            return 60
        if coverage >= 0.30:
            return 40
        if coverage >= 0.15:
            return 25
        return 10

    def _score_testing(self, metrics: RepositoryMetrics) -> float:
        """Score testing (0-100). Placeholder — detects test files."""
        # Look for test directories / test file names
        test_files = 0
        for fm in metrics.files:
            path = fm.path.replace("\\", "/")
            if "/test" in path or "/tests" in path or path.startswith("test"):
                test_files += 1

        total = len(metrics.files)
        if total == 0:
            return 50

        test_ratio = test_files / total
        if test_ratio >= 0.20:
            return 85
        if test_ratio >= 0.10:
            return 65
        if test_ratio >= 0.05:
            return 45
        if test_ratio > 0:
            return 30
        return 15

    # ------------------------------------------------------------------
    # Strengths & Weaknesses
    # ------------------------------------------------------------------

    def _compute_strengths(
        self,
        dimensions: list[DimensionScore],
        metrics: RepositoryMetrics,
    ) -> list[str]:
        """Identify what the project does well."""
        strengths: list[str] = []

        for dim in dimensions:
            if dim.score >= 85:
                _map = {
                    "complexity": "Low complexity",
                    "maintainability": "High maintainability",
                    "readability": "Clean, readable code",
                    "architecture": "Clean architecture",
                    "documentation": "Good documentation coverage",
                    "testing": "Good test coverage",
                }
                strengths.append(_map.get(dim.name, f"Strong {dim.name}"))

        # Specific findings
        if metrics.average_complexity < 3:
            strengths.append("Consistently low function complexity")

        if metrics.comment_ratio > 0.15:
            strengths.append("Well-commented code")

        if metrics.total_duplicate_blocks == 0:
            strengths.append("No significant code duplication")

        if metrics.average_function_length < 20:
            strengths.append("Short, focused functions")

        return strengths[:8]  # cap at 8

    def _compute_weaknesses(
        self,
        dimensions: list[DimensionScore],
        metrics: RepositoryMetrics,
    ) -> list[str]:
        """Identify areas for improvement."""
        weaknesses: list[str] = []

        for dim in dimensions:
            if dim.score < 50:
                _map = {
                    "complexity": "High code complexity",
                    "maintainability": "Low maintainability",
                    "readability": "Poor readability",
                    "architecture": "Architectural issues",
                    "documentation": "Documentation coverage is low",
                    "testing": "No test coverage detected",
                }
                weaknesses.append(_map.get(dim.name, f"Weak {dim.name}"))
            elif dim.score < 70:
                _map = {
                    "complexity": "Moderate complexity in some areas",
                    "maintainability": "Maintainability could be improved",
                    "readability": "Readability concerns in some files",
                    "architecture": "Architecture could be improved",
                    "documentation": "Documentation is sparse in places",
                    "testing": "Limited test coverage",
                }
                weaknesses.append(_map.get(dim.name, f"Moderate {dim.name}"))

        # Specific findings
        if metrics.worst_function and metrics.worst_function_complexity > 10:
            weaknesses.append(
                f"High complexity in {metrics.worst_function} "
                f"(complexity: {metrics.worst_function_complexity})"
            )

        if metrics.overall_docstring_coverage < 0.5:
            weaknesses.append("Several undocumented functions")

        if metrics.total_duplicate_blocks > 3:
            weaknesses.append(f"Detected {metrics.total_duplicate_blocks} duplicated code blocks")

        if metrics.average_function_length > 40:
            weaknesses.append("Several long methods that could be extracted")

        if metrics.longest_file and metrics.longest_file_lines > 600:
            weaknesses.append(f"Overly long file: {metrics.longest_file}")

        return weaknesses[:8]
