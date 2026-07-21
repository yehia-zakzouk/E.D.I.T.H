"""Dashboard Metrics — aggregates health data across projects.

Used for:
    - Overall EDITH statistics
    - Cross-project comparisons
    - Trend aggregation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.history.review_history import ReviewHistory
from app.learning.statistics import mean, median, stdev


@dataclass
class AggregateMetrics:
    """Aggregate metrics across all projects."""
    total_projects: int = 0
    total_reviews: int = 0
    total_decisions: int = 0
    average_health: float = 0.0
    median_health: float = 0.0
    health_std: float = 0.0
    dimension_averages: dict[str, float] = field(default_factory=dict)


def compute_aggregates(review_history: ReviewHistory) -> AggregateMetrics:
    """Compute aggregate metrics across all reviewed projects."""
    all_reviews = review_history.get_reviews(limit=1000)

    if not all_reviews:
        return AggregateMetrics()

    # Group by project
    project_reviews: dict[str, list] = {}
    for review in all_reviews:
        path = review.project_path
        if path not in project_reviews:
            project_reviews[path] = []
        project_reviews[path].append(review)

    # Get latest review per project
    latest: list = []
    for path, reviews in project_reviews.items():
        latest.append(max(reviews, key=lambda r: r.timestamp or ""))

    # Compute health stats
    health_scores = [r.overall_score for r in latest]
    total_reviews = len(all_reviews)

    # Dimension averages
    dims = ["complexity", "maintainability", "readability", "architecture", "documentation"]
    dim_avgs = {
        d: round(mean([getattr(r, d, 0) for r in latest]), 1)
        for d in dims
    }

    return AggregateMetrics(
        total_projects=len(project_reviews),
        total_reviews=total_reviews,
        average_health=round(mean(health_scores), 1),
        median_health=round(median(health_scores), 1),
        health_std=round(stdev(health_scores), 1),
        dimension_averages=dim_avgs,
    )
