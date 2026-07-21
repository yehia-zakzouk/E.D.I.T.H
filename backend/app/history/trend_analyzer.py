"""Trend Analyzer (Sprint 8.2) — compares reviews over time to detect
improvements, regressions, and compute deltas.

Instead of showing a single score, EDITH says things like:
    - "Architecture improved by 5 points since last scan."
    - "Complexity is trending up — 3 consecutive increases."
    - "Documentation dropped 12 points after the refactor."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import logger
from app.history.review_history import ReviewHistory, ReviewRunRecord


@dataclass
class DimensionTrend:
    """Trend information for a single dimension."""
    dimension: str
    current: float = 0.0
    previous: float = 0.0
    delta: float = 0.0
    delta_pct: float = 0.0
    direction: str = "stable"  # "improved" | "declined" | "stable"
    consecutive_direction: int = 0  # how many reviews in same direction


@dataclass
class TrendReport:
    """Complete trend analysis between two review snapshots."""
    project_path: str = ""
    project_name: str = ""
    current_timestamp: str = ""
    previous_timestamp: str = ""
    overall_delta: float = 0.0
    dimensions: list[DimensionTrend] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    def text(self) -> str:
        lines: list[str] = []
        lines.append("=" * 55)
        lines.append(f"  TREND ANALYSIS — {self.project_name}")
        lines.append("=" * 55)
        lines.append("")

        if self.overall_delta is not None:
            direction = "▲ improved" if self.overall_delta > 0 else "▼ declined" if self.overall_delta < 0 else "● stable"
            lines.append(f"  Overall: {direction} by {abs(self.overall_delta):.1f} points")
            lines.append("")

        lines.append("  ── Dimension Changes ──")
        for d in self.dimensions:
            icon = "↑" if d.delta > 0 else "↓" if d.delta < 0 else "→"
            lines.append(
                f"  {d.dimension:18s}  {d.current:5.1f}  "
                f"{icon} {d.delta:+5.1f}  ({d.delta_pct:+.0f}%)  {d.direction}"
            )

        lines.append("")
        if self.findings:
            lines.append("  ── Key Findings ──")
            for f in self.findings:
                lines.append(f"  • {f}")

        lines.append("")
        lines.append("=" * 55)
        return "\n".join(lines)


class TrendAnalyzer:
    """Analyses review trends across multiple runs.

    Usage::

        analyzer = TrendAnalyzer(review_history)
        report = analyzer.compare(project_path)
        print(report.text())
    """

    DIMENSIONS = ["complexity", "maintainability", "readability", "architecture", "documentation", "testing"]

    def __init__(self, review_history: ReviewHistory):
        self._history = review_history

    def compare_latest(self, project_path: str) -> TrendReport:
        """Compare the two most recent reviews for a project."""
        latest = self._history.get_latest_review(project_path)
        previous = self._history.get_previous_review(project_path)

        if latest is None:
            return TrendReport(project_path=project_path)

        return self._compute_trend(latest, previous)

    def compare_reviews(
        self, current: ReviewRunRecord, previous: ReviewRunRecord,
    ) -> TrendReport:
        return self._compute_trend(current, previous)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _compute_trend(
        self, current: ReviewRunRecord, previous: Optional[ReviewRunRecord],
    ) -> TrendReport:
        if previous is None:
            return TrendReport(
                project_path=current.project_path,
                project_name=current.project_name,
                current_timestamp=current.timestamp,
                findings=["First review — no baseline to compare against."],
            )

        dimensions: list[DimensionTrend] = []
        findings: list[str] = []

        for dim in self.DIMENSIONS:
            cur_val = getattr(current, dim, 0)
            prev_val = getattr(previous, dim, 0)
            delta = round(cur_val - prev_val, 1)
            delta_pct = round((delta / max(prev_val, 0.1)) * 100, 1)

            # Determine direction
            if delta > 1.0:
                direction = "improved"
            elif delta < -1.0:
                direction = "declined"
            else:
                direction = "stable"

            dimensions.append(DimensionTrend(
                dimension=dim,
                current=cur_val,
                previous=prev_val,
                delta=delta,
                delta_pct=delta_pct,
                direction=direction,
            ))

            # Generate findings for significant changes
            if abs(delta) >= 5:
                if direction == "improved":
                    findings.append(
                        f"{dim.capitalize()} improved by {delta:.0f} points "
                        f"(from {prev_val:.0f} to {cur_val:.0f})"
                    )
                elif direction == "declined":
                    findings.append(
                        f"{dim.capitalize()} declined by {abs(delta):.0f} points "
                        f"(from {prev_val:.0f} to {cur_val:.0f})"
                    )

        overall_delta = round(current.overall_score - (previous.overall_score or 0), 1)

        return TrendReport(
            project_path=current.project_path,
            project_name=current.project_name,
            current_timestamp=current.timestamp,
            previous_timestamp=previous.timestamp,
            overall_delta=overall_delta,
            dimensions=dimensions,
            findings=findings,
        )

    def get_all_reviews_for_project(self, project_path: str) -> list[ReviewRunRecord]:
        return self._history.get_reviews(project_path, limit=100)
