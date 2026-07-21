"""Review Report — generates formatted output from the scoring + metrics.

Produces:
    * Human-readable text report (with strengths, weaknesses, recs)
    * Structured dict (for LLM consumption)
    * Optional JSON for external tools
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.review.metrics import RepositoryMetrics
from app.review.scoring import ReviewScore, DimensionScore


@dataclass
class ReviewReport:
    """Complete review report with text and structured data."""

    project_name: str
    metrics: RepositoryMetrics
    score: ReviewScore
    text: str = ""
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project": self.project_name,
            "overall_score": self.score.overall,
            "rating": self.score.rating,
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "weight": d.weight,
                    "rating": d.rating,
                }
                for d in self.score.dimensions
            ],
            "strengths": self.score.strengths,
            "weaknesses": self.score.weaknesses,
            "recommendations": self.recommendations,
            "metrics": {
                "total_files": self.metrics.total_files,
                "total_lines": self.metrics.total_lines,
                "total_symbols": self.metrics.total_symbols,
                "average_complexity": self.metrics.average_complexity,
                "average_function_length": self.metrics.average_function_length,
                "worst_function": self.metrics.worst_function,
                "worst_function_complexity": self.metrics.worst_function_complexity,
                "largest_class": self.metrics.largest_class,
                "longest_file": self.metrics.longest_file,
                "docstring_coverage": self.metrics.overall_docstring_coverage,
                "duplicate_blocks": self.metrics.total_duplicate_blocks,
            },
        }


class ReportGenerator:
    """Generates formatted review reports from scoring results."""

    def generate(
        self,
        project_name: str,
        metrics: RepositoryMetrics,
        score: ReviewScore,
    ) -> ReviewReport:
        """Generate the full review report with text and recommendations."""
        text = self._build_text_report(project_name, metrics, score)
        recommendations = self._build_recommendations(score, metrics)

        return ReviewReport(
            project_name=project_name,
            metrics=metrics,
            score=score,
            text=text,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Text report
    # ------------------------------------------------------------------

    def _build_text_report(
        self,
        project_name: str,
        metrics: RepositoryMetrics,
        score: ReviewScore,
    ) -> str:
        """Build the human-readable text report (see the example in docs)."""
        lines: list[str] = []
        sep = "=" * 55

        lines.append(sep)
        lines.append(f"  ENGINEERING REVIEW — {project_name}")
        lines.append(sep)
        lines.append("")
        lines.append(f"  Overall Score:  {score.overall}/100  ({score.rating.upper()})")
        lines.append("")

        # Dimension breakdown
        lines.append("  ── Dimensions ──")
        for d in score.dimensions:
            bar = self._score_bar(d.score)
            lines.append(
                f"  {d.name:18s}  {d.score:5.1f}  {bar}  ({d.rating})"
            )
        lines.append("")

        # Summary stats
        lines.append("  ── Summary ──")
        lines.append(f"  Files:                {metrics.total_files}")
        lines.append(f"  Lines of code:        {metrics.total_code_lines}")
        lines.append(f"  Total symbols:        {metrics.total_symbols}")
        lines.append(f"  Average complexity:   {metrics.average_complexity:.1f}")
        lines.append(f"  Avg function length:  {metrics.average_function_length:.0f} lines")
        if metrics.worst_function:
            lines.append(f"  Worst function:       {metrics.worst_function} "
                         f"(complexity: {metrics.worst_function_complexity})")
        if metrics.largest_class:
            lines.append(f"  Largest class:        {metrics.largest_class} "
                         f"({metrics.largest_class_lines} lines)")
        if metrics.longest_file:
            lines.append(f"  Longest file:         {metrics.longest_file} "
                         f"({metrics.longest_file_lines} lines)")
        lines.append(f"  Docstring coverage:   {metrics.overall_docstring_coverage:.0%}")
        if metrics.total_duplicate_blocks > 0:
            lines.append(f"  Duplicate blocks:     {metrics.total_duplicate_blocks}")
        lines.append("")

        # Strengths
        if score.strengths:
            lines.append("  ── Strengths ──")
            for s in score.strengths:
                lines.append(f"  ✓ {s}")
            lines.append("")

        # Weaknesses
        if score.weaknesses:
            lines.append("  ── Weaknesses ──")
            for w in score.weaknesses:
                lines.append(f"  • {w}")
            lines.append("")

        # Recommendations
        recs = self._build_recommendations(score, metrics)
        if recs:
            lines.append("  ── Recommendations ──")
            for i, rec in enumerate(recs, 1):
                lines.append(f"  {i}. {rec}")
            lines.append("")

        lines.append(sep)
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _build_recommendations(
        self,
        score: ReviewScore,
        metrics: RepositoryMetrics,
    ) -> list[str]:
        """Generate actionable recommendations based on the score/metrics."""
        recommendations: list[str] = []

        # Complexity recommendations
        if metrics.worst_function and metrics.worst_function_complexity > 10:
            recommendations.append(
                f"Reduce complexity in {metrics.worst_function} "
                f"(cyclomatic complexity: {metrics.worst_function_complexity}). "
                "Consider extracting smaller helper functions."
            )

        if metrics.average_function_length > 40:
            recommendations.append(
                f"Average function length is {metrics.average_function_length:.0f} lines. "
                "Aim for functions under 20 lines by extracting logic into helpers."
            )

        # Documentation recommendations
        if metrics.overall_docstring_coverage < 0.5:
            recommendations.append(
                "Add docstrings to undocumented functions and classes. "
                f"Current coverage is {metrics.overall_docstring_coverage:.0%}."
            )

        # Duplication
        if metrics.total_duplicate_blocks > 3:
            recommendations.append(
                f"Found {metrics.total_duplicate_blocks} duplicated code blocks. "
                "Consider extracting shared logic into utility functions."
            )

        # Large files
        if metrics.longest_file and metrics.longest_file_lines > 600:
            recommendations.append(
                f"Split {metrics.longest_file} ({metrics.longest_file_lines} lines) "
                "into smaller, focused modules."
            )

        # Large classes
        if metrics.largest_class and metrics.largest_class_lines > 400:
            recommendations.append(
                f"Split {metrics.largest_class} ({metrics.largest_class_lines} lines) "
                "following the Single Responsibility Principle."
            )

        # Testing
        low_testing = next(
            (d for d in score.dimensions if d.name == "testing" and d.score < 40),
            None,
        )
        if low_testing:
            recommendations.append(
                "Add unit tests. The project has few or no test files detected."
            )

        # Architecture (if layer violations or cycles exist)
        arch_dim = next((d for d in score.dimensions if d.name == "architecture"), None)
        if arch_dim and arch_dim.score < 60:
            recommendations.append(
                "Review module dependencies for architectural issues. "
                "Consider extracting shared code into dedicated modules."
            )

        return recommendations[:8]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_bar(score: float, width: int = 20) -> str:
        """Render a simple ASCII bar chart for a score."""
        filled = max(0, min(width, int(score / 100 * width)))
        empty = width - filled
        filled_char = "█"
        empty_char = "░"
        return filled_char * filled + empty_char * empty
