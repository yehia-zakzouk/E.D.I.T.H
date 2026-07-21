"""EDITH Dashboard Package (Sprint 8.7–8.10) — repository health,
timelines, and predictive metrics.

Packages
--------
dashboard/
    repository_health.py  — Health dashboard (8.7)
    timeline.py           — Repository timeline (8.8)
    metrics.py            — Metrics aggregation
"""

from app.dashboard.repository_health import RepositoryHealth
from app.dashboard.timeline import Timeline

__all__ = ["RepositoryHealth", "Timeline"]
