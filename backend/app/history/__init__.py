"""EDITH History Package (Sprint 8.1–8.3) — stores every review, decision,
and trend analysis permanently so EDITH builds engineering memory over time.

Packages
--------
history/         — review + decision persistence, trend analysis
learning/        — knowledge base, pattern mining, personalization
dashboard/       — health metrics, timeline, repository health
"""

from app.history.history_engine import HistoryEngine
from app.history.review_history import ReviewHistory
from app.history.decision_history import DecisionHistory
from app.history.trend_analyzer import TrendAnalyzer

__all__ = ["HistoryEngine", "ReviewHistory", "DecisionHistory", "TrendAnalyzer"]
