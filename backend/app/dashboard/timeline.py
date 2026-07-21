"""Repository Timeline (Sprint 8.8) — visualizes a project's engineering
evolution over time.

Shows:
    - Score history across all dimensions
    - When decisions were made
    - Annotated milestones
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import logger
from app.history.review_history import ReviewHistory, ReviewRunRecord
from app.history.decision_history import DecisionHistory
from app.learning.statistics import trend_direction, predict_next


@dataclass
class TimelinePoint:
    """A single point on the timeline."""
    timestamp: str = ""
    overall_score: float = 0.0
    dimensions: dict[str, float] = field(default_factory=dict)
    is_decision_point: bool = False
    decision_label: str = ""


@dataclass
class TimelineReport:
    """Complete timeline for a project."""
    project_path: str = ""
    points: list[TimelinePoint] = field(default_factory=list)
    overall_trend: str = "stable"
    prediction: Optional[float] = None

    def text(self) -> str:
        lines: list[str] = []
        sep = "-" * 55

        lines.append(sep)
        lines.append("  REPOSITORY TIMELINE")
        lines.append(sep)
        lines.append("")

        if not self.points:
            lines.append("  No review history yet.")
            lines.append("")
            lines.append(sep)
            return "\n".join(lines)

        lines.append(f"  Period: {self.points[0].timestamp[:10]} → {self.points[-1].timestamp[:10]}")
        lines.append(f"  Reviews: {len(self.points)}")
        lines.append(f"  Trend: {self.overall_trend}")

        if self.prediction is not None:
            lines.append(f"  Predicted next score: {self.prediction:.0f}/100")

        lines.append("")
        lines.append("  ── Score History ──")
        for pt in self.points:
            marker = " ◆" if pt.is_decision_point else ""
            label = f" — {pt.decision_label}" if pt.decision_label else ""
            lines.append(
                f"  {pt.timestamp[:16]:16s}  {pt.overall_score:5.1f}{marker}{label}"
            )
        lines.append("")
        lines.append("  ── Key Dimensions ──")
        dims_to_show = ["complexity", "maintainability", "architecture", "documentation"]
        for dim in dims_to_show:
            values = [pt.dimensions.get(dim, 0) for pt in self.points if pt.dimensions]
            if values:
                direction = trend_direction(values)
                icon = "↑" if direction == "improving" else "↓" if direction == "declining" else "→"
                pred = predict_next(values)
                pred_str = f" (next: {pred:.0f})" if pred is not None else ""
                lines.append(f"  {dim:18s}  {values[0]:5.0f} → {values[-1]:5.0f}  {icon}  {direction}{pred_str}")

        lines.append("")
        lines.append(sep)
        return "\n".join(lines)


class Timeline:
    """Builds a repository timeline from review and decision history.

    Usage::

        timeline = Timeline(review_history, decision_history)
        report = timeline.build(project_path)
        print(report.text())
    """

    def __init__(
        self,
        review_history: ReviewHistory,
        decision_history: DecisionHistory,
    ):
        self._rh = review_history
        self._dh = decision_history

    def build(self, project_path: str) -> TimelineReport:
        """Build a timeline from all stored reviews for a project."""
        reviews = self._rh.get_reviews(project_path, limit=100)
        if not reviews:
            return TimelineReport(project_path=project_path)

        # Get decisions for annotation
        decisions = self._dh.get_recent_problems(limit=50, project_path=project_path)
        decision_times: set[str] = {d.timestamp[:10] for d in decisions if d.timestamp}

        points: list[TimelinePoint] = []
        for review in reviews:
            date_key = review.timestamp[:10]
            is_decision = date_key in decision_times

            points.append(TimelinePoint(
                timestamp=review.timestamp,
                overall_score=review.overall_score,
                dimensions={
                    "complexity": review.complexity,
                    "maintainability": review.maintainability,
                    "readability": review.readability,
                    "architecture": review.architecture,
                    "documentation": review.documentation,
                    "testing": review.testing,
                },
                is_decision_point=is_decision,
                decision_label="Decision point" if is_decision else "",
            ))

        # Compute trend
        scores = [p.overall_score for p in points]
        overall_trend = trend_direction(scores)
        prediction = predict_next(scores)

        return TimelineReport(
            project_path=project_path,
            points=points,
            overall_trend=overall_trend,
            prediction=prediction,
        )
