"""Statistics utilities for EDITH's learning and dashboard systems.

Simple statistical operations used by knowledge base, pattern mining,
and the dashboard — no external dependencies.
"""

from __future__ import annotations

import math
from typing import Optional


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_v[mid - 1] + sorted_v[mid]) / 2
    return sorted_v[mid]


def stdev(values: list[float]) -> float:
    """Population standard deviation."""
    if len(values) < 2:
        return 0.0
    m = mean(values)
    variance = sum((v - m) ** 2 for v in values) / len(values)
    return math.sqrt(variance)


def min_max_normalize(value: float, min_v: float, max_v: float) -> float:
    """Normalize a value to [0, 1] range."""
    if max_v == min_v:
        return 0.5
    return (value - min_v) / (max_v - min_v)


def weighted_average(values: list[float], weights: list[float]) -> float:
    if not values or not weights or len(values) != len(weights):
        return 0.0
    total_weight = sum(weights)
    if total_weight == 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_weight


def trend_direction(
    values: list[float],
    threshold: float = 0.05,
) -> str:
    """Determine if a sequence is trending up, down, or stable."""
    if len(values) < 2:
        return "stable"

    # Simple linear regression slope
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = mean(values)

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return "stable"

    slope = numerator / denominator
    relative_slope = slope / max(abs(y_mean), 0.01)

    if relative_slope > threshold:
        return "improving"
    elif relative_slope < -threshold:
        return "declining"
    return "stable"


def predict_next(values: list[float]) -> Optional[float]:
    """Simple linear projection for the next value in a sequence.

    Uses ordinary least squares. Returns None if there's insufficient data.
    """
    if len(values) < 2:
        return None

    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = mean(values)

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return y_mean

    slope = numerator / denominator
    intercept = y_mean - slope * x_mean

    # Predict the next point (index = n)
    return intercept + slope * n
