"""Repository Health (Sprint 8.7) — the dashboard's home screen.

Shows:
    - Overall health score with trend
    - Per-dimension scores with trend arrows
    - Technical debt estimate
    - Recent decisions summary
    - Improvement recommendations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import logger
from app.history.review_history import ReviewHistory, ReviewRunRecord
from app.history.decision_history import DecisionHistory
from app.history.trend_analyzer import TrendAnalyzer


@dataclass
class HealthSnapshot:
    """A point-in-time health snapshot for a project."""
    project_path: str = ""
    overall_score: float = 0.0
    overall_trend: str = "stable"  # "improving" | "declining" | "stable"
    overall_delta: float = 0.0
    complexity: float = 0.0
    maintainability: float = 0.0
    readability: float = 0.0
    architecture: float = 0.0
    documentation: float = 0.0
    testing: float = 0.0
    dimensions: dict[str, dict] = field(default_factory=dict)
    technical_debt_estimate: float = 0.0
    total_reviews: int = 0
    total_decisions: int = 0
    recent_findings: list[str] = field(default_factory=list)


class RepositoryHealth:
    """Computes and presents repository health from stored history.

    Usage::

        health = RepositoryHealth(review_history, decision_history)
        snapshot = health.get_health(project_path)
        print(f"Overall: {snapshot.overall_score}")
        print(f"Trend: {snapshot.overall_trend}")
    """

    def __init__(
        self,
        review_history: ReviewHistory,
        decision_history: DecisionHistory,
    ):
        self._rh = review_history
        self._dh = decision_history
        self._trends = TrendAnalyzer(review_history)

    def get_health(self, project_path: str) -> HealthSnapshot:
        """Compute the current health snapshot for a project."""
        latest = self._rh.get_latest_review(project_path)
        if latest is None:
            return HealthSnapshot(project_path=project_path)

        # Get trend data
        trend = self._trends.compare_latest(project_path)

        # Compute dimension details
        dimensions: dict[str, dict] = {}
        for d in trend.dimensions:
            dimensions[d.dimension] = {
                "current": d.current,
                "previous": d.previous,
                "delta": d.delta,
                "direction": d.direction,
            }

        # Technical debt estimate (inverted docstring coverage + complexity)
        doc_penalty = (1 - latest.docstring_coverage) * 30
        complexity_penalty = max(0, (latest.avg_complexity - 3) * 5)
        debt_estimate = min(100, round(doc_penalty + complexity_penalty, 1))

        # Counts
        total_reviews = self._rh.get_review_count(project_path)
        total_decisions = len(self._dh.get_recent_problems(
            limit=100, project_path=project_path,
        ))

        # Recent findings from the latest review
        recent_findings: list[str] = []
        if latest.summary:
            import json
            try:
                data = json.loads(latest.summary)
                recent_findings.extend(data.get("weaknesses", [])[:3])
            except Exception:
                pass

        return HealthSnapshot(
            project_path=project_path,
            overall_score=latest.overall_score,
            overall_trend=trend.dimensions[0].direction if trend.dimensions else "stable",
            overall_delta=trend.overall_delta,
            complexity=latest.complexity,
            maintainability=latest.maintainability,
            readability=latest.readability,
            architecture=latest.architecture,
            documentation=latest.documentation,
            testing=latest.testing,
            dimensions=dimensions,
            technical_debt_estimate=debt_estimate,
            total_reviews=total_reviews,
            total_decisions=total_decisions,
            recent_findings=recent_findings,
        )

    def dashboard_text(self, project_path: str) -> str:
        """Generate a formatted dashboard text report."""
        health = self.get_health(project_path)
        lines: list[str] = []
        sep = "=" * 55

        lines.append(sep)
        lines.append(f"  REPOSITORY HEALTH — {project_path.split('/')[-1]}")
        lines.append(sep)
        lines.append("")

        # Overall score with trend arrow
        arrow = "▲" if health.overall_delta > 0 else "▼" if health.overall_delta < 0 else "●"
        lines.append(f"  Overall Score:  {health.overall_score:.0f}/100  {arrow} {abs(health.overall_delta):.0f}")
        lines.append("")

        # Dimensions
        lines.append("  ── Dimensions ──")
        dim_names = ["complexity", "maintainability", "readability", "architecture", "documentation", "testing"]
        for dim in dim_names:
            val = getattr(health, dim, 0)
            info = health.dimensions.get(dim, {})
            delta = info.get("delta", 0)
            direction = info.get("direction", "stable")
            icon = "↑" if direction == "improved" else "↓" if direction == "declined" else "→"
            lines.append(f"  {dim:18s}  {val:5.0f}  {icon} {delta:+.0f}")

        lines.append("")
        lines.append(f"  Technical Debt:  {health.technical_debt_estimate:.0f}/100")
        lines.append(f"  Reviews:         {health.total_reviews}")
        lines.append(f"  Decisions:       {health.total_decisions}")

        if health.recent_findings:
            lines.append("")
            lines.append("  ── Recent Findings ──")
            for f in health.recent_findings:
                lines.append(f"  • {f}")

        lines.append("")
        lines.append(sep)
        return "\n".join(lines)
