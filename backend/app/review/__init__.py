"""EDITH Engineering Review Engine.

Evaluates code quality across five dimensions:
    - Complexity
    - Maintainability
    - Readability
    - Architecture
    - Duplication

Usage::

    from app.review.review_engine import ReviewEngine

    engine = ReviewEngine()
    report = engine.review(project)
    print(report.text)
"""
from app.review.review_engine import ReviewEngine
from app.review.metrics import RepositoryMetrics
from app.review.scoring import ReviewScore
from app.review.report import ReviewReport
from app.review.visualizer import CouplingGraphVisualizer

__all__ = [
    "ReviewEngine",
    "RepositoryMetrics",
    "ReviewScore",
    "ReviewReport",
    "CouplingGraphVisualizer",
]
